import os

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from src.access import access
from src.config import config
from src.server import app


def make_png(path):
    Image.new("RGB", (8, 8), "red").save(path, "PNG")


@pytest.fixture
def share(tmp_path, monkeypatch):
    """Shares tmp_path/shared and returns its path. Everything else in tmp_path must stay unreachable.

    tmp_path/
        shared/                     <- the shared folder
            hello.txt
            photo.png
            docs/notes.txt
        shared-private/secret.png   <- sibling whose name starts with "shared"
        outside.png
    """
    root = tmp_path / "shared"
    (root / "docs").mkdir(parents=True)
    (root / "hello.txt").write_text("hello")
    make_png(root / "photo.png")
    (root / "docs" / "notes.txt").write_text("notes")

    (tmp_path / "shared-private").mkdir()
    make_png(tmp_path / "shared-private" / "secret.png")
    make_png(tmp_path / "outside.png")

    cache = tmp_path / "cache"
    cache.mkdir()

    monkeypatch.setattr(config, "ROOT_DIR", str(root))
    monkeypatch.setattr(config, "ALLOW_UPLOAD", False)
    monkeypatch.setattr(config, "UPLOAD_DIR", "")
    monkeypatch.setattr(config, "THUMB_CACHE_DIR", cache)
    access.start(require_code=False)
    return root


@pytest.fixture
def code_on(share):
    """Turns the access code on and returns it."""
    return access.start(require_code=True)


@pytest.fixture
def client(share):
    return TestClient(app, base_url="http://127.0.0.1:8000")


@pytest.fixture
def link_out(share):
    """A symlink inside the shared folder that points at a folder outside it."""
    link = share / "link"
    try:
        os.symlink(share.parent / "shared-private", link, target_is_directory=True)
    except OSError:
        pytest.skip("Can't create symlinks here (Windows without Developer Mode)")
    return link
