import asyncio
import os
import threading
import weakref
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import AsyncIterator, Callable, Iterator

import anyio
import anyio.lowlevel

from src.paths import is_hidden, is_listable, resolves_inside

MAX_ZIPS = 2
CHUNK_BYTES = 1024 * 1024

_free = threading.BoundedSemaphore(MAX_ZIPS)
pool = ThreadPoolExecutor(max_workers=MAX_ZIPS, thread_name_prefix="zip")


class _Slot:
    """One of the MAX_ZIPS. Freed once, by release() or when nothing refers to it any more."""
    def __init__(self):
        self.release = weakref.finalize(self, _free.release)


class _Output:
    """A write-only stream that zipfile writes into and the generator empties."""
    def __init__(self):
        self.parts = []
        self.size = 0

    def write(self, data) -> int:
        self.parts.append(bytes(data))
        self.size += len(data)
        return len(data)

    def flush(self):
        pass

    def take(self) -> bytes:
        data = b"".join(self.parts)
        self.parts, self.size = [], 0
        return data


def zip_members(folder: Path, root: Path, skip: Path | None) -> Iterator[tuple[Path, str]]:
    """Regular files under folder that the listing would show, with their names in the ZIP. root and skip must be resolved."""
    for dirpath, dirnames, filenames in os.walk(folder, followlinks=False):
        here = Path(dirpath)
        if skip and resolves_inside(here, skip):
            dirnames.clear()
            continue
        dirnames[:] = [d for d in dirnames if not is_hidden(here / d)]
        for name in filenames:
            path = here / name
            if is_listable(path, root) and path.is_file():
                yield path, path.relative_to(folder).as_posix()


def _add(zf: zipfile.ZipFile, path: Path, name: str, out: _Output) -> Iterator[bytes]:
    try:
        src = open(path, "rb")
    except OSError:
        return  # Unreadable: left out, and the rest of the ZIP still completes
    with src:
        info = zipfile.ZipInfo.from_file(path, name, strict_timestamps=False)
        info.compress_type = zipfile.ZIP_DEFLATED
        with zf.open(info, "w") as dest:
            while block := src.read(CHUNK_BYTES):
                dest.write(block)
                if out.size >= CHUNK_BYTES:
                    yield out.take()


def _chunks(folder: Path, root: Path, skip: Path | None, slot: _Slot) -> Iterator[bytes]:
    try:
        out = _Output()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for path, name in zip_members(folder, root, skip):
                yield from _add(zf, path, name, out)
        yield out.take()
    finally:
        slot.release()


class ZipStream:
    """A ZIP's chunks. close() stops the work and frees the slot, whether or not it started."""
    def __init__(self, chunks: Iterator[bytes], slot: _Slot):
        self._chunks, self._slot = chunks, slot

    def __iter__(self):
        return self

    def __next__(self) -> bytes:
        return next(self._chunks)

    def close(self):
        try:
            self._chunks.close()
        finally:
            self._slot.release()


def zip_stream(folder: Path, root: Path, skip: Path | None) -> ZipStream | None:
    """folder as a ZIP, in chunks, or None if MAX_ZIPS are already running.

    Closing or dropping the stream, started or not, stops the work and frees the slot.
    """
    if not _free.acquire(blocking=False):
        return None
    slot = _Slot()
    return ZipStream(_chunks(folder, root, skip, slot), slot)


async def in_pool(work: Callable, *args):
    """work(*args) in the ZIP pool. Shielded: a cancelled request waits for it rather than leave it running."""
    with anyio.CancelScope(shield=True):
        return await asyncio.wrap_future(pool.submit(work, *args))


async def chunks_in_pool(stream: ZipStream) -> AsyncIterator[bytes]:
    """stream's chunks, each one made in the ZIP pool. The caller closes stream when it's done."""
    while (chunk := await in_pool(next, stream, None)) is not None:
        yield chunk
        await anyio.lowlevel.checkpoint()  # Where a request whose client went away is cancelled
