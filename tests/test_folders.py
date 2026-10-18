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


def test_a_path_with_a_nul_character_is_refused_not_raised(home):
    message = refuse_share_folder(str(home / "Photos") + "\x00x")
    assert message and "\x00" not in message


@pytest.mark.skipif(sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                    reason="needs POSIX permissions and a non-root user")
def test_a_path_inside_an_unreadable_folder_is_refused_not_raised(home):
    locked = home / "locked"
    (locked / "inner").mkdir(parents=True)
    locked.chmod(0)
    try:
        message = refuse_share_folder(str(locked / "inner"))
    finally:
        locked.chmod(0o700)
    assert message and str(locked) not in message


@pytest.fixture
def no_os_folders(monkeypatch):
    """The fake home lives under the temp dir, which can itself sit inside an OS folder (/private/var on macOS)."""
    monkeypatch.setattr("src.paths._os_folders", lambda: [])


def test_the_parent_of_home_is_refused(home, no_os_folders):
    assert refuse_share_folder(str(home.parent)) is not None


def test_a_folder_further_above_home_is_refused(home, no_os_folders):
    assert refuse_share_folder(str(home.parent.parent)) is not None


def test_the_parent_of_home_is_refused_when_reached_through_a_symlink(home, no_os_folders, tmp_path):
    link = tmp_path / "parent-link"
    try:
        os.symlink(home.parent, link, target_is_directory=True)
    except OSError:
        pytest.skip("Can't create symlinks here (Windows without Developer Mode)")
    assert refuse_share_folder(str(link)) is not None


def test_the_message_for_a_folder_holding_home_names_no_path(home, no_os_folders):
    message = refuse_share_folder(str(home.parent))
    assert message and str(home.parent) not in message


def test_a_sibling_of_home_is_allowed(home, no_os_folders):
    sibling = home.parent / "Shared"
    sibling.mkdir()
    assert refuse_share_folder(str(sibling)) is None


def test_a_subfolder_of_home_is_still_allowed_when_its_parent_is_refused(home, no_os_folders):
    (home / "Photos" / "2026").mkdir(parents=True)
    assert refuse_share_folder(str(home / "Photos" / "2026")) is None
