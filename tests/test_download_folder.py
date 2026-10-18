import io
import shutil
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from src.config import config
from src.server import app


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 1, 1, 12, 0, 0, tzinfo=tz)


@pytest.fixture
def overlapping_zips(monkeypatch):
    """Two folder downloads whose ZIPs are being built at the same time, like two big folders.

    The clock is frozen so a timestamp-based ZIP name collides every time, and each ZIP is held
    until both have been built so neither response is sent before the other ZIP is written.
    """
    monkeypatch.setattr("src.server.datetime", FrozenDatetime, raising=False)

    real_make_archive = shutil.make_archive
    one_at_a_time = threading.Lock()
    both_built = threading.Barrier(2, timeout=5)

    def make_archive(*args, **kwargs):
        with one_at_a_time:
            result = real_make_archive(*args, **kwargs)
        both_built.wait()
        return result

    monkeypatch.setattr(shutil, "make_archive", make_archive)


def zip_contents(content):
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        return {name: z.read(name) for name in z.namelist()}


def test_concurrent_folder_downloads_each_get_their_own_folder(client, share, overlapping_zips):
    (share / "music").mkdir()
    (share / "music" / "song.txt").write_text("la la")

    with ThreadPoolExecutor(max_workers=2) as pool:
        docs, music = pool.map(lambda path: client.get("/api/download_folder", params={"path": path}),
                               ["docs", "music"])

    assert docs.status_code == music.status_code == 200
    assert 'filename="docs.zip"' in docs.headers["content-disposition"]
    assert 'filename="music.zip"' in music.headers["content-disposition"]
    assert zip_contents(docs.content) == {"notes.txt": b"notes"}
    assert zip_contents(music.content) == {"song.txt": b"la la"}


def test_folder_zip_is_deleted_after_it_is_sent(client):
    r = client.get("/api/download_folder", params={"path": "docs"})
    assert r.status_code == 200
    assert zip_contents(r.content) == {"notes.txt": b"notes"}
    assert list(config.THUMB_CACHE_DIR.iterdir()) == []


def test_partial_zip_is_deleted_when_zipping_fails(share, monkeypatch):
    def make_archive(base_name, format, root_dir):
        # Like the real one when a file in the folder can't be read: part of the ZIP is already on disk
        with open(f"{base_name}.zip", "wb") as f:
            f.write(b"PK\x03\x04partial")
        raise PermissionError(f"Can't read a file in {root_dir}")

    monkeypatch.setattr(shutil, "make_archive", make_archive)

    r = TestClient(app, base_url="http://127.0.0.1:8000", raise_server_exceptions=False).get("/api/download_folder", params={"path": "docs"})
    assert r.status_code == 500
    assert list(config.THUMB_CACHE_DIR.iterdir()) == []
