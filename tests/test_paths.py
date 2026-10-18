import io
import os
import zipfile

import pytest

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


@pytest.fixture
def link_out(share):
    """A symlink inside the shared folder that points at a folder outside it."""
    link = share / "link"
    try:
        os.symlink(share.parent / "shared-private", link, target_is_directory=True)
    except OSError:
        pytest.skip("Can't create symlinks here (Windows without Developer Mode)")
    return link


@pytest.mark.parametrize("endpoint", FILE_ENDPOINTS)
def test_file_endpoints_refuse_symlinks_out(client, link_out, endpoint):
    assert client.get(f"/api/{endpoint}", params={"path": "link/secret.png"}).status_code == 403


@pytest.mark.parametrize("endpoint", FOLDER_ENDPOINTS)
def test_folder_endpoints_refuse_symlinks_out(client, link_out, endpoint):
    assert client.get(f"/api/{endpoint}", params={"path": "link"}).status_code == 403
