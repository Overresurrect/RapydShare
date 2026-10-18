import os
import stat
import sys
from pathlib import Path

import pytest

from src.paths import refuse_share_folder


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A made-up home folder, so no test depends on the real one."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


def test_a_subfolder_of_home_is_allowed(home):
    (home / "Photos").mkdir()
    assert refuse_share_folder(str(home / "Photos")) is None


def test_home_itself_is_refused(home):
    assert refuse_share_folder(str(home)) is not None


def test_home_is_refused_when_reached_through_a_symlink(home, tmp_path):
    link = tmp_path / "link"
    try:
        os.symlink(home, link, target_is_directory=True)
    except OSError:
        pytest.skip("Can't create symlinks here (Windows without Developer Mode)")
    assert refuse_share_folder(str(link)) is not None


@pytest.mark.parametrize("folder", ["", "   "])
def test_an_empty_path_is_refused(home, folder):
    assert refuse_share_folder(folder) is not None


def test_a_missing_folder_is_refused(home):
    assert refuse_share_folder(str(home / "nope")) is not None


def test_a_file_is_refused(home):
    (home / "a.txt").write_text("a")
    assert refuse_share_folder(str(home / "a.txt")) is not None


def test_the_system_root_is_refused(home):
    root = os.environ.get("SystemDrive", "C:") + "\\" if sys.platform == "win32" else "/"
    assert refuse_share_folder(root) is not None


if sys.platform == "win32":
    OS_FOLDERS = [os.environ.get(name) for name in ("SystemRoot", "ProgramFiles", "ProgramData")]
else:
    OS_FOLDERS = ["/System", "/Library", "/Applications", "/usr", "/bin", "/etc", "/private", "/var"]


@pytest.mark.parametrize("folder", OS_FOLDERS)
def test_os_folders_are_refused(home, folder):
    if not folder or not Path(folder).is_dir():
        pytest.skip("Not on this machine")
    assert refuse_share_folder(folder) is not None


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX paths")
def test_a_folder_inside_an_os_folder_is_refused(home):
    assert refuse_share_folder("/usr/bin") is not None


def test_a_hidden_folder_is_refused(home):
    (home / ".ssh").mkdir()
    assert refuse_share_folder(str(home / ".ssh")) is not None


def test_a_folder_inside_a_hidden_folder_is_refused(home):
    (home / ".config" / "app").mkdir(parents=True)
    assert refuse_share_folder(str(home / ".config" / "app")) is not None


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS flag")
def test_a_folder_with_the_os_hidden_flag_is_refused(home):
    library = home / "Library"
    (library / "Mail").mkdir(parents=True)
    os.chflags(library, stat.UF_HIDDEN)
    assert refuse_share_folder(str(library)) is not None
    assert refuse_share_folder(str(library / "Mail")) is not None


def test_the_message_names_no_path(home):
    assert str(home) not in refuse_share_folder(str(home))
