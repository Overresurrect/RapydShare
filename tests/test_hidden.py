import os
import stat
import sys

import pytest
from PIL import Image

from src import paths
from src.paths import is_hidden, is_hidden_name, resolves_inside

FILE_ENDPOINTS = ["download", "view", "thumb"]
FOLDER_ENDPOINTS = ["files", "download_folder"]
BASE_LISTING = {"hello.txt", "photo.png", "docs"}


def make_png(path):
    Image.new("RGB", (8, 8), "red").save(path, "PNG")


def listed_names(client, path=""):
    r = client.get("/api/files", params={"path": path})
    assert r.status_code == 200
    return {item["name"] for item in r.json()}


def assert_not_found(client, endpoint, path):
    r = client.get(f"/api/{endpoint}", params={"path": path})
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}


# --- Names ---

@pytest.mark.parametrize("name", [
    ".env", ".DS_Store", ".git", "desktop.ini", "DESKTOP.INI", "Thumbs.db", "thumbs.DB",
    "$RECYCLE.BIN", "$Recycle.Bin", "System Volume Information", "system volume information",
])
def test_hidden_names(name):
    assert is_hidden_name(name)


@pytest.mark.parametrize("name", ["hello.txt", "env", "a.b", "Thumbs.db.txt", "my desktop.ini"])
def test_ordinary_names(name):
    assert not is_hidden_name(name)


def test_is_hidden_checks_the_name(share):
    (share / ".env").write_text("x")
    assert is_hidden(share / ".env")
    assert not is_hidden(share / "hello.txt")


# --- Dot-files and deny-listed names ---

@pytest.fixture
def hidden_share(share):
    """Adds hidden entries to the shared folder; each one holds or is a PNG so every endpoint could serve it."""
    make_png(share / ".photo.png")
    make_png(share / "THUMBS.DB")
    (share / ".git").mkdir()
    make_png(share / ".git" / "pic.png")
    (share / "$Recycle.Bin").mkdir()
    make_png(share / "$Recycle.Bin" / "pic.png")
    make_png(share / "docs" / "Desktop.ini")
    return share


def test_hidden_entries_are_left_out_of_the_listing(client, hidden_share):
    assert listed_names(client) == BASE_LISTING
    assert listed_names(client, "docs") == {"notes.txt"}


@pytest.mark.parametrize("endpoint", FILE_ENDPOINTS)
@pytest.mark.parametrize("path", [".photo.png", "THUMBS.DB", ".git/pic.png", "$Recycle.Bin/pic.png",
                                  "docs/Desktop.ini", "docs/../.photo.png"])
def test_hidden_files_are_404(client, hidden_share, endpoint, path):
    assert_not_found(client, endpoint, path)


@pytest.mark.parametrize("endpoint", FOLDER_ENDPOINTS)
@pytest.mark.parametrize("path", [".git", "$Recycle.Bin"])
def test_hidden_folders_are_404(client, hidden_share, endpoint, path):
    assert_not_found(client, endpoint, path)


@pytest.fixture
def links_to_hidden(hidden_share):
    """Symlinks with ordinary names pointing at hidden entries, and a hidden-named link to an ordinary folder."""
    try:
        os.symlink(hidden_share / ".git", hidden_share / "visible", target_is_directory=True)
        os.symlink(hidden_share / ".photo.png", hidden_share / "visible.png")
        os.symlink(hidden_share / "docs", hidden_share / ".docs", target_is_directory=True)
    except OSError:
        pytest.skip("Can't create symlinks here (Windows without Developer Mode)")
    return hidden_share


def test_links_to_hidden_entries_are_left_out_of_the_listing(client, links_to_hidden):
    os.symlink(links_to_hidden / ".git" / "pic.png", links_to_hidden / "inside-git.png")
    assert listed_names(client) == BASE_LISTING


@pytest.mark.parametrize("endpoint", FILE_ENDPOINTS)
@pytest.mark.parametrize("path", ["visible/pic.png", "visible.png", ".docs/notes.txt"])
def test_links_into_or_through_hidden_entries_are_404(client, links_to_hidden, endpoint, path):
    assert_not_found(client, endpoint, path)


# --- The OS hidden flag ---

def set_hidden_flag(path, attributes):
    if sys.platform == "darwin":
        os.chflags(path, stat.UF_HIDDEN)
    else:
        import ctypes
        assert ctypes.windll.kernel32.SetFileAttributesW(str(path), attributes)


@pytest.fixture(params=["hidden", "system"])
def flagged_share(request, share):
    """A flagged file and a flagged folder holding a PNG. macOS has one flag, so both params set UF_HIDDEN."""
    if sys.platform not in ("darwin", "win32"):
        pytest.skip("No OS hidden flag on this platform")
    attributes = getattr(stat, f"FILE_ATTRIBUTE_{request.param.upper()}", 0)
    make_png(share / "flagged.png")
    (share / "flagged").mkdir()
    make_png(share / "flagged" / "pic.png")
    set_hidden_flag(share / "flagged.png", attributes)
    set_hidden_flag(share / "flagged", attributes)
    return share


def test_is_hidden_checks_the_flag(flagged_share):
    assert is_hidden(flagged_share / "flagged.png")
    assert is_hidden(flagged_share / "flagged")


def test_flagged_entries_are_left_out_of_the_listing(client, flagged_share):
    assert listed_names(client) == BASE_LISTING


def test_links_to_flagged_entries_are_left_out_of_the_listing(client, flagged_share):
    try:
        os.symlink(flagged_share / "flagged.png", flagged_share / "link.png")
        os.symlink(flagged_share / "flagged", flagged_share / "link", target_is_directory=True)
    except OSError:
        pytest.skip("Can't create symlinks here (Windows without Developer Mode)")
    assert listed_names(client) == BASE_LISTING


@pytest.mark.parametrize("endpoint", FILE_ENDPOINTS)
@pytest.mark.parametrize("path", ["flagged.png", "flagged/pic.png"])
def test_flagged_files_are_404(client, flagged_share, endpoint, path):
    assert_not_found(client, endpoint, path)


@pytest.mark.parametrize("endpoint", FOLDER_ENDPOINTS)
def test_flagged_folders_are_404(client, flagged_share, endpoint):
    assert_not_found(client, endpoint, "flagged")


# --- Symlinks out of the share ---

def test_resolves_inside(share, link_out):
    root = share.resolve()
    assert resolves_inside(share / "docs", root)
    assert not resolves_inside(link_out, root)
    assert not resolves_inside(share.parent / "outside.png", root)


def test_symlink_out_is_left_out_of_the_listing(client, link_out):
    assert listed_names(client) == BASE_LISTING


def test_symlink_inside_is_listed(client, share):
    try:
        os.symlink(share / "docs", share / "docs-link", target_is_directory=True)
    except OSError:
        pytest.skip("Can't create symlinks here (Windows without Developer Mode)")
    assert listed_names(client) == BASE_LISTING | {"docs-link"}


# --- Names the path check refuses ---

@pytest.mark.skipif(sys.platform == "win32", reason="Windows doesn't allow these names")
@pytest.mark.parametrize("name", ["a:b.txt", "a\\b.txt", "x\\.env"])
def test_names_the_path_check_refuses_are_left_out_of_the_listing(client, share, name):
    # Listed means downloadable: resolve_in_root refuses ":", and "\" reads as a folder
    (share / "docs" / name).write_text("x")
    (share / name).mkdir()
    assert listed_names(client, "docs") == {"notes.txt"}
    assert listed_names(client) == BASE_LISTING


# --- Speed ---

def test_plain_entries_are_listed_without_resolving_each_one(client, share, monkeypatch):
    for i in range(20):
        (share / "docs" / f"{i}.txt").write_text("x")
        (share / "docs" / f"folder{i}").mkdir()
    resolved = []
    monkeypatch.setattr(paths, "resolves_inside", lambda p, root: resolved.append(p) or True)
    assert len(listed_names(client, "docs")) == 41
    assert resolved == []


def test_symlinked_entries_are_still_resolved(client, share, link_out, monkeypatch):
    resolved = []
    real = paths.resolves_inside
    monkeypatch.setattr(paths, "resolves_inside", lambda p, root: resolved.append(p.name) or real(p, root))
    assert listed_names(client) == BASE_LISTING
    assert resolved == ["link"]
