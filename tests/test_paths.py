import io
import os
import sys
import zipfile

import pytest
from fastapi.testclient import TestClient

from src.config import config
from src.server import app

FILE_ENDPOINTS = ["download", "view", "thumb"]
FOLDER_ENDPOINTS = ["files", "download_folder"]


# --- Requests inside the shared folder work ---

def test_lists_the_shared_folder(client):
    r = client.get("/api/files", params={"path": ""})
    assert r.status_code == 200
    items = {item["name"]: item for item in r.json()}
    assert set(items) == {"hello.txt", "photo.png", "docs"}
    assert (items["docs"]["path"], items["docs"]["is_dir"], items["docs"]["type"]) == ("docs", True, "folder")
    assert (items["photo.png"]["path"], items["photo.png"]["type"]) == ("photo.png", "image")
    assert (items["hello.txt"]["type"], items["hello.txt"]["size"]) == ("file", 5)


def test_lists_a_subfolder_with_forward_slash_paths(client):
    r = client.get("/api/files", params={"path": "docs"})
    assert r.status_code == 200
    assert [item["path"] for item in r.json()] == ["docs/notes.txt"]


def test_downloads_a_file_as_an_attachment(client):
    r = client.get("/api/download", params={"path": "docs/notes.txt"})
    assert r.status_code == 200
    assert r.content == b"notes"
    assert 'attachment; filename="notes.txt"' in r.headers["content-disposition"]


def test_views_a_file_inline(client):
    r = client.get("/api/view", params={"path": "hello.txt"})
    assert r.status_code == 200
    assert r.content == b"hello"
    assert "attachment" not in r.headers.get("content-disposition", "")


def test_makes_a_jpeg_thumbnail(client):
    r = client.get("/api/thumb", params={"path": "photo.png"})
    assert r.status_code == 200
    assert r.content[:3] == b"\xff\xd8\xff"


def test_downloads_a_folder_as_a_zip(client):
    r = client.get("/api/download_folder", params={"path": "docs"})
    assert r.status_code == 200
    assert 'filename="docs.zip"' in r.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert z.read("notes.txt") == b"notes"


def test_dot_dot_that_stays_inside_is_allowed(client):
    r = client.get("/api/download", params={"path": "docs/../hello.txt"})
    assert r.status_code == 200
    assert r.content == b"hello"


@pytest.mark.parametrize("endpoint", ["files", "download", "view", "thumb"])
def test_missing_path_is_404(client, endpoint):
    assert client.get(f"/api/{endpoint}", params={"path": "nope"}).status_code == 404


# --- Nothing outside the shared folder is reachable ---

@pytest.mark.parametrize("endpoint", FILE_ENDPOINTS)
@pytest.mark.parametrize("path", [
    "../outside.png",
    "docs/../../outside.png",
    "../shared-private/secret.png",
])
def test_file_endpoints_refuse_relative_escapes(client, endpoint, path):
    assert client.get(f"/api/{endpoint}", params={"path": path}).status_code == 403


@pytest.mark.parametrize("endpoint", FOLDER_ENDPOINTS)
@pytest.mark.parametrize("path", ["..", "docs/../..", "../shared-private"])
def test_folder_endpoints_refuse_relative_escapes(client, endpoint, path):
    assert client.get(f"/api/{endpoint}", params={"path": path}).status_code == 403


@pytest.mark.parametrize("endpoint", FILE_ENDPOINTS)
def test_file_endpoints_refuse_absolute_paths(client, share, endpoint):
    path = str(share.parent / "outside.png")
    assert client.get(f"/api/{endpoint}", params={"path": path}).status_code == 403


@pytest.mark.parametrize("endpoint", FOLDER_ENDPOINTS)
def test_folder_endpoints_refuse_absolute_paths(client, share, endpoint):
    path = str(share.parent / "shared-private")
    assert client.get(f"/api/{endpoint}", params={"path": path}).status_code == 403


@pytest.mark.parametrize("endpoint", FILE_ENDPOINTS)
def test_file_endpoints_refuse_symlinks_out(client, link_out, endpoint):
    assert client.get(f"/api/{endpoint}", params={"path": "link/secret.png"}).status_code == 403


@pytest.mark.parametrize("endpoint", FOLDER_ENDPOINTS)
def test_folder_endpoints_refuse_symlinks_out(client, link_out, endpoint):
    assert client.get(f"/api/{endpoint}", params={"path": "link"}).status_code == 403


# --- Odd and platform-specific inputs ---

ALL_ENDPOINTS = FILE_ENDPOINTS + FOLDER_ENDPOINTS


@pytest.mark.parametrize("endpoint", ALL_ENDPOINTS)
def test_no_shared_folder_is_503(client, monkeypatch, endpoint):
    monkeypatch.setattr(config, "ROOT_DIR", "")
    assert client.get(f"/api/{endpoint}", params={"path": ""}).status_code == 503


@pytest.mark.parametrize("endpoint", ALL_ENDPOINTS)
@pytest.mark.parametrize("path", ["//host/x", "\\\\host\\x", "C:x", "C:\\x", "a\x00b", "hello.txt:x"])
def test_unsafe_text_is_403(client, endpoint, path):
    assert client.get(f"/api/{endpoint}", params={"path": path}).status_code == 403


@pytest.fixture
def lenient_client(share):
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("endpoint", ALL_ENDPOINTS)
@pytest.mark.parametrize("path", ["x" * 1000, "docs/" + "x" * 300 + "/y", "hello.txt/x"],
                         ids=["long-path", "long-name", "file-as-folder"])
def test_odd_paths_are_a_generic_404(lenient_client, endpoint, path):
    r = lenient_client.get(f"/api/{endpoint}", params={"path": path})
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}


@pytest.mark.parametrize("endpoint, path", [
    ("files", "hello.txt"),
    ("view", "docs"),
    ("download", "docs"),
    ("thumb", "docs"),
    ("thumb", "album.png"),
], ids=["file-to-files", "folder-to-view", "folder-to-download", "folder-to-thumb", "image-named-folder-to-thumb"])
def test_wrong_kind_is_a_4xx_not_500(lenient_client, share, endpoint, path):
    (share / "album.png").mkdir()
    r = lenient_client.get(f"/api/{endpoint}", params={"path": path})
    assert 400 <= r.status_code < 500


def test_unreadable_folder_is_403(lenient_client, share, monkeypatch):
    def refuse(path):
        raise PermissionError(13, "Permission denied", str(path))
    monkeypatch.setattr("src.server.os.scandir", refuse)
    r = lenient_client.get("/api/files", params={"path": "docs"})
    assert r.status_code == 403
    assert "docs" not in r.text


def test_folder_gone_while_listing_is_404(lenient_client, share, monkeypatch):
    def gone(path):
        raise FileNotFoundError(2, "No such file or directory", str(path))
    monkeypatch.setattr("src.server.os.scandir", gone)
    r = lenient_client.get("/api/files", params={"path": "docs"})
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}


def test_symlink_loop_is_a_generic_404(lenient_client, share):
    try:
        os.symlink(share / "loop", share / "loop")
    except OSError:
        pytest.skip("Can't create symlinks here (Windows without Developer Mode)")
    assert lenient_client.get("/api/view", params={"path": "loop"}).status_code == 404


@pytest.mark.skipif(sys.platform != "win32", reason="Windows strips trailing dots and spaces")
@pytest.mark.parametrize("path", ["hello.txt.", "hello.txt ", "docs./notes.txt", "docs /notes.txt"])
def test_windows_aliases_are_404(client, path):
    assert client.get("/api/view", params={"path": path}).status_code == 404


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS named forks")
def test_named_forks_are_404(client, share):
    (share / "hello.txt" / "..namedfork" / "rsrc").write_bytes(b"fork")
    assert client.get("/api/view", params={"path": "hello.txt/..namedfork/rsrc"}).status_code == 404
