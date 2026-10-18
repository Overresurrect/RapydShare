import pytest
from fastapi.testclient import TestClient
from PIL import Image

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
    monkeypatch.setattr(config, "USE_AUTH", False)
    monkeypatch.setattr(config, "USERNAME", "admin")
    monkeypatch.setattr(config, "PASSWORD", "1234")
    monkeypatch.setattr(config, "ALLOW_UPLOAD", False)
    monkeypatch.setattr(config, "UPLOAD_DIR", "")
    monkeypatch.setattr(config, "THUMB_CACHE_DIR", cache)
    return root


@pytest.fixture
def client(share):
    return TestClient(app)
