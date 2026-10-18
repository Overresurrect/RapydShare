import unicodedata

import pytest

from src.uploads import numbered_names, sanitize_filename


@pytest.mark.parametrize("name,expected", [
    ("photo.jpg", "photo.jpg"),
    # Folders in the name are dropped
    ("../../etc/passwd", "passwd"),
    ("..\\..\\boot.ini", "boot.ini"),
    # Characters Windows doesn't allow in file names
    ('a<b>c:d"e|f?g*h.txt', "a_b_c_d_e_f_g_h.txt"),
    ("tab\there.txt", "tab_here.txt"),
    # Windows drops trailing dots and spaces, so names ending in them don't round-trip
    ("  report.txt  ", "report.txt"),
    ("report.", "report"),
    (". .report.txt. . ", "report.txt"),
    # Nothing left after cleaning
    ("", "unnamed"),
    ("...", "unnamed"),
    (" . ", "unnamed"),
    ("/", "unnamed"),
    # Windows device names, which can't be used as file names even with an extension
    ("CON", "_CON"),
    ("con.txt", "_con.txt"),
    ("LPT9.log", "_LPT9.log"),
    ("aux.tar.gz", "_aux.tar.gz"),
    ("CONSOLE.txt", "CONSOLE.txt"),
    ("COM0.txt", "_COM0.txt"),
    ("LPT0", "_LPT0"),
    ("conin$.txt", "_conin$.txt"),
    ("CONOUT$", "_CONOUT$"),
    ("COM¹.txt", "_COM¹.txt"),
    ("lpt³", "_lpt³"),
    ("nul .txt", "_nul .txt"),
    ("COM10.txt", "COM10.txt"),
    # Non-ASCII and emoji are kept
    ("résumé 🎉.pdf", "résumé 🎉.pdf"),
    ("写真.jpg", "写真.jpg"),
])
def test_sanitize_filename(name, expected):
    assert sanitize_filename(name) == expected


def test_names_are_nfc_normalized():
    decomposed = unicodedata.normalize("NFD", "résumé.txt")
    assert decomposed != "résumé.txt"
    assert sanitize_filename(decomposed) == "résumé.txt"


@pytest.mark.parametrize("char", [
    "‮",    # right-to-left override (Cf), which can make "exe.txt" display as "txt.exe"
    "​",    # zero-width space (Cf)
    "﻿",    # byte order mark (Cf)
    "\x7f",      # delete (Cc)
    "\x85",      # next line (Cc)
    "\ud800",    # lone surrogate (Cs)
    "",    # private use (Co)
    "\U000e0080",  # unassigned (Cn)
    " ",    # line separator (Zl)
    " ",    # paragraph separator (Zp)
])
def test_invisible_and_control_characters_are_replaced(char):
    assert sanitize_filename(f"a{char}b.txt") == "a_b.txt"


@pytest.mark.parametrize("name,expected", [
    ("site.url", "site.url.txt"),
    ("app.lnk", "app.lnk.txt"),
    ("explorer.SCF", "explorer.SCF.txt"),
    ("docs.library-ms", "docs.library-ms.txt"),
    ("search.searchConnector-ms", "search.searchConnector-ms.txt"),
    ("desktop.ini", "desktop.ini.txt"),
    ("Desktop.INI", "Desktop.INI.txt"),
    ("site.url. ", "site.url.txt"),
    ("my.desktop.ini", "my.desktop.ini"),
    ("lnk", "lnk"),
])
def test_risky_windows_types_get_txt_appended(name, expected):
    assert sanitize_filename(name) == expected


def test_long_names_are_capped_keeping_the_extension():
    name = sanitize_filename("a" * 300 + ".jpg")
    assert len(name.encode("utf-8")) == 200
    assert name == "a" * 196 + ".jpg"


def test_capping_never_splits_a_character():
    name = sanitize_filename("🎉" * 100 + ".jpg")
    assert len(name.encode("utf-8")) <= 200
    assert name == "🎉" * 49 + ".jpg"


def test_capping_a_name_without_an_extension_drops_trailing_dots_and_spaces():
    name = sanitize_filename("a" * 199 + " " + "b" * 50)
    assert name == "a" * 199


def test_a_reserved_name_stays_safe_and_within_the_cap():
    name = sanitize_filename("aux." + "b" * 196)
    assert len(name.encode("utf-8")) <= 200
    assert name.startswith("_")


def test_numbered_names():
    names = numbered_names("report.txt")
    assert [next(names) for _ in range(3)] == ["report.txt", "report (1).txt", "report (2).txt"]
    names = numbered_names("README")
    assert [next(names) for _ in range(2)] == ["README", "README (1)"]
    names = numbered_names("archive.tar.gz")
    assert [next(names) for _ in range(2)] == ["archive.tar.gz", "archive.tar (1).gz"]
