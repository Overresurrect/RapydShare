import io
import os
import stat
import sys
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from src import zipstream
from src.config import config
from src.server import app
from src.zipstream import MAX_ZIPS, zip_stream


def zip_contents(content):
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        return {name: z.read(name) for name in z.namelist()}


def download(client, path="docs"):
    r = client.get("/api/download_folder", params={"path": path})
    assert r.status_code == 200
    return zip_contents(r.content)


def files_under(folder):
    return sorted(folder.rglob("*"))


def symlink(target, link, is_dir=False):
    try:
        os.symlink(target, link, target_is_directory=is_dir)
    except OSError:
        pytest.skip("Can't create symlinks here (Windows without Developer Mode)")


@pytest.fixture
def held(share):
    """Takes ZIP slots directly, as running downloads would, and frees whatever is left at the end."""
    streams = []

    def take():
        stream = zip_stream(share.resolve(), share.resolve(), None)
        if stream is not None:
            streams.append(stream)
        return stream

    yield take
    for stream in streams:
        list(stream)  # Runs each to the end, so its slot is freed now rather than when it's collected


# --- Concurrent downloads and the disk ---

def test_concurrent_folder_downloads_each_get_their_own_folder(client, share, monkeypatch):
    (share / "music").mkdir()
    (share / "music" / "song.txt").write_text("la la")

    # Both ZIPs are being written at the same time, like two big folders
    real_members = zipstream.zip_members
    both_started = threading.Barrier(2, timeout=5)

    def zip_members(*args):
        both_started.wait()
        yield from real_members(*args)

    monkeypatch.setattr(zipstream, "zip_members", zip_members)

    with ThreadPoolExecutor(max_workers=2) as pool:
        docs, music = pool.map(lambda path: client.get("/api/download_folder", params={"path": path}),
                               ["docs", "music"])

    assert docs.status_code == music.status_code == 200
    assert docs.headers["content-disposition"] == 'attachment; filename="docs.zip"'
    assert music.headers["content-disposition"] == 'attachment; filename="music.zip"'
    assert zip_contents(docs.content) == {"notes.txt": b"notes"}
    assert zip_contents(music.content) == {"song.txt": b"la la"}


def test_folder_zip_leaves_nothing_in_the_cache_folder(client):
    assert download(client) == {"notes.txt": b"notes"}
    assert list(config.THUMB_CACHE_DIR.iterdir()) == []


def test_failed_zip_leaves_nothing_on_disk_and_frees_its_slot(share, held, monkeypatch, tmp_path):
    def zip_members(folder, root, skip):
        yield folder / "notes.txt", "notes.txt"
        raise PermissionError("Can't read the folder")

    before = files_under(tmp_path)
    with monkeypatch.context() as m:
        m.setattr(zipstream, "zip_members", zip_members)
        client = TestClient(app, base_url="http://127.0.0.1:8000", raise_server_exceptions=False)
        client.get("/api/download_folder", params={"path": "docs"})

    assert files_under(tmp_path) == before
    assert all(held() is not None for _ in range(MAX_ZIPS))


def test_non_ascii_folder_name_uses_the_utf8_filename_form(client, share):
    (share / "фото").mkdir()
    (share / "фото" / "a.txt").write_text("a")
    r = client.get("/api/download_folder", params={"path": "фото"})
    assert r.status_code == 200
    assert r.headers["content-disposition"] == "attachment; filename*=utf-8''%D1%84%D0%BE%D1%82%D0%BE.zip"
    assert r.headers["content-type"] == "application/zip"


# --- What goes in the ZIP ---

def test_subfolders_are_kept(client, share):
    (share / "docs" / "sub").mkdir()
    (share / "docs" / "sub" / "deep.txt").write_text("deep")
    assert download(client) == {"notes.txt": b"notes", "sub/deep.txt": b"deep"}


def test_hidden_entries_are_left_out(client, share):
    (share / "docs" / ".env").write_text("secret")
    (share / "docs" / "Thumbs.db").write_text("x")
    (share / "docs" / ".git").mkdir()
    (share / "docs" / ".git" / "config").write_text("x")
    (share / "docs" / "$Recycle.Bin").mkdir()
    (share / "docs" / "$Recycle.Bin" / "old.txt").write_text("x")
    assert download(client) == {"notes.txt": b"notes"}


def set_hidden_flag(path):
    if sys.platform == "darwin":
        os.chflags(path, stat.UF_HIDDEN)
    else:
        import ctypes
        assert ctypes.windll.kernel32.SetFileAttributesW(str(path), stat.FILE_ATTRIBUTE_HIDDEN)


@pytest.mark.skipif(sys.platform not in ("darwin", "win32"), reason="No OS hidden flag on this platform")
def test_flagged_entries_are_left_out(client, share):
    (share / "docs" / "flagged.txt").write_text("x")
    (share / "docs" / "flagged").mkdir()
    (share / "docs" / "flagged" / "in.txt").write_text("x")
    set_hidden_flag(share / "docs" / "flagged.txt")
    set_hidden_flag(share / "docs" / "flagged")
    assert download(client) == {"notes.txt": b"notes"}


def test_symlinks_out_of_the_share_are_left_out(client, share):
    symlink(share.parent / "shared-private", share / "docs" / "out", is_dir=True)
    symlink(share.parent / "outside.png", share / "docs" / "outside.png")
    assert download(client) == {"notes.txt": b"notes"}


def test_symlinks_to_hidden_entries_are_left_out(client, share):
    (share / ".env").write_text("secret")
    symlink(share / ".env", share / "docs" / "env.txt")
    assert download(client) == {"notes.txt": b"notes"}


def test_symlinks_that_stay_inside_are_included(client, share):
    symlink(share / "hello.txt", share / "docs" / "hello-link.txt")
    assert download(client) == {"notes.txt": b"notes", "hello-link.txt": b"hello"}


def test_the_cache_folder_is_left_out(client, share, monkeypatch):
    cache = share / "docs" / "cache"
    cache.mkdir()
    (cache / "thumb.jpg").write_text("x")
    monkeypatch.setattr(config, "THUMB_CACHE_DIR", cache)
    assert download(client) == {"notes.txt": b"notes"}
    assert download(client, "docs/cache") == {}


def test_zips_without_a_cache_folder(client, monkeypatch):
    monkeypatch.setattr(config, "THUMB_CACHE_DIR", None)
    assert download(client) == {"notes.txt": b"notes"}


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="Needs POSIX permissions and a non-root user")
def test_an_unreadable_file_is_skipped(client, share):
    locked = share / "docs" / "locked.txt"
    locked.write_text("x")
    locked.chmod(0)
    try:
        assert download(client) == {"notes.txt": b"notes"}
    finally:
        locked.chmod(0o644)


def test_an_old_timestamp_is_clamped(client, share):
    os.utime(share / "docs" / "notes.txt", (0, 0))
    assert download(client) == {"notes.txt": b"notes"}


# --- Streaming and the concurrency limit ---

def test_a_large_file_streams_in_several_chunks(share):
    data = os.urandom(4 * 1024 * 1024)
    (share / "docs" / "big.bin").write_bytes(data)
    chunks = list(zip_stream(share / "docs", share.resolve(), None))
    assert len(chunks) > 1
    assert zip_contents(b"".join(chunks)) == {"notes.txt": b"notes", "big.bin": data}


def test_a_third_concurrent_zip_gets_503(client, held):
    assert held() is not None
    assert held() is not None
    r = client.get("/api/download_folder", params={"path": "docs"})
    assert r.status_code == 503
    assert r.headers["retry-after"] == "5"
    assert r.json() == {"detail": "Service Unavailable"}


def test_a_finished_zip_frees_its_slot(client, held):
    for _ in range(MAX_ZIPS + 1):
        download(client)
    assert all(held() is not None for _ in range(MAX_ZIPS))


def test_an_abandoned_stream_frees_its_slot(held, share):
    # Starlette stops asking for chunks and drops the iterator when the client goes away
    dropped = zip_stream(share.resolve(), share.resolve(), None)
    closed = zip_stream(share.resolve(), share.resolve(), None)
    next(dropped)
    next(closed)
    del dropped
    closed.close()
    assert all(held() is not None for _ in range(MAX_ZIPS))


def test_a_stream_that_never_started_frees_its_slot(held, share):
    unstarted = zip_stream(share.resolve(), share.resolve(), None)
    assert unstarted is not None
    del unstarted
    assert all(held() is not None for _ in range(MAX_ZIPS))
