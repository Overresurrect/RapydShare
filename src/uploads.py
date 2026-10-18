import ctypes
import ctypes.util
import itertools
import logging
import os
import shutil
import sys
import time
import unicodedata
from pathlib import Path

import aiofiles
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

log = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 20 * 1024 ** 3
MIN_FREE_BYTES = 1024 ** 3
CHECK_FREE_EVERY = 64 * 1024 ** 2
MAX_NAME_BYTES = 200

RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
                  *(f"{device}{n}" for device in ("COM", "LPT") for n in "0123456789¹²³")}
# Windows acts on these by itself (shortcuts, folder settings), so they get .txt appended
RISKY_SUFFIXES = (".url", ".lnk", ".scf", ".library-ms", ".searchconnector-ms")
# Control, format (bidi overrides, zero-width), surrogate, private, unassigned and line/paragraph separators
INVISIBLE_CATEGORIES = {"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"}


def _clean_char(c: str) -> str:
    return "_" if c in '<>:"/\\|?*' or unicodedata.category(c) in INVISIBLE_CATEGORIES else c


def _split_ext(name: str) -> tuple[str, str]:
    stem, dot, ext = name.rpartition(".")
    return (stem, dot + ext) if stem else (name, "")


def _cap(name: str) -> str:
    """Cuts name to MAX_NAME_BYTES of UTF-8, keeping the extension and never splitting a character."""
    if len(name.encode("utf-8")) <= MAX_NAME_BYTES:
        return name
    stem, ext = _split_ext(name)
    if len(ext.encode("utf-8")) >= MAX_NAME_BYTES:
        stem, ext = name, ""
    budget = MAX_NAME_BYTES - len(ext.encode("utf-8"))
    stem = stem.encode("utf-8")[:budget].decode("utf-8", "ignore")
    return (stem + ext).rstrip(" .")


def sanitize_filename(name: str) -> str:
    name = unicodedata.normalize("NFC", name)
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(map(_clean_char, name)).strip(" .")
    # Capping first, since cutting a long name can leave a risky or reserved one. Neither fix below undoes the other
    name = _cap(name)
    if not name:
        return "unnamed"
    if name.lower().endswith(RISKY_SUFFIXES) or name.lower() == "desktop.ini":
        name = _cap(name + ".txt")  # .txt is the extension, so capping keeps it
    # Windows treats "aux.tar.gz" and "aux .txt" like "aux", so check everything before the first dot
    if name.split(".", 1)[0].rstrip().upper() in RESERVED_NAMES:
        name = _cap("_" + name)
    return name


def numbered_names(name: str):
    """name, then "name (1).ext", "name (2).ext" and so on."""
    yield name
    stem, ext = _split_ext(name)
    for i in itertools.count(1):
        yield f"{stem} ({i}){ext}"


def declared_length(text: str | None) -> int:
    if text is None:
        raise HTTPException(411)
    if not (text.isascii() and text.isdigit()):
        raise HTTPException(400)
    if int(text) > MAX_UPLOAD_BYTES:
        raise HTTPException(413)
    return int(text)


def free_space(folder: Path) -> int:
    return shutil.disk_usage(folder).free


def has_room(folder: Path, more_bytes: int) -> bool:
    return free_space(folder) - more_bytes >= MIN_FREE_BYTES


async def _open_part(folder: Path, name: str):
    # Hidden, so a partial upload is never served. Numbered like the final name when another upload has it open
    for candidate in numbered_names(name):
        part = folder / f".{candidate}.part"
        try:
            return part, await aiofiles.open(part, "xb")
        except FileExistsError:
            continue


def _move_into_place(part: Path, folder: Path, name: str) -> Path:
    """Claims the first free name with an exclusive create, then moves part over it."""
    for candidate in numbered_names(name):
        target = folder / candidate
        try:
            os.close(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL))
        except FileExistsError:
            continue
        try:
            os.replace(part, target)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return target


async def save_upload(chunks, folder: Path, name: str, length: int) -> Path:
    """Streams chunks (length bytes in all) into folder under a free version of name. Nothing is left behind on failure."""
    part, out = await _open_part(folder, name)
    try:
        size = 0
        next_check = CHECK_FREE_EVERY
        try:
            async for chunk in chunks:
                size += len(chunk)
                if size > length:
                    raise HTTPException(400)
                await out.write(chunk)
                if size >= next_check:
                    if not await run_in_threadpool(has_room, folder, length - size):
                        raise HTTPException(507)
                    next_check += CHECK_FREE_EVERY
        finally:
            await out.close()
        if size != length:
            raise HTTPException(400)
        target = await run_in_threadpool(_move_into_place, part, folder, name)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    await run_in_threadpool(mark_downloaded, target)
    return target


def _quarantine(path: Path):
    # Python has no setxattr on macOS
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    libc.setxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p,
                              ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
    value = f"0081;{int(time.time()):08x};RapydShare;".encode()
    if libc.setxattr(os.fsencode(path), b"com.apple.quarantine", value, len(value), 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "setxattr failed")


def mark_downloaded(path: Path):
    """Best effort: marks a saved upload as coming from another device, so the OS warns before opening it."""
    try:
        # The packaged Mac app quarantines what it writes by itself (LSFileQuarantineEnabled)
        if sys.platform == "darwin" and not getattr(sys, "frozen", False):
            _quarantine(path)
        elif sys.platform == "win32":
            with open(f"{path}:Zone.Identifier", "wb") as f:
                f.write(b"[ZoneTransfer]\r\nZoneId=3")
    except Exception:
        log.warning("Couldn't mark an upload as downloaded", exc_info=True)
