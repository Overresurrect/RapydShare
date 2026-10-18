import pytest

from src.server import sanitize_filename


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
    # Nothing left after cleaning
    ("", "unnamed"),
    ("...", "unnamed"),
    ("/", "unnamed"),
    # Windows device names, which can't be used as file names even with an extension
    ("CON", "_CON"),
    ("con.txt", "_con.txt"),
    ("LPT9.log", "_LPT9.log"),
    ("CONSOLE.txt", "CONSOLE.txt"),
])
def test_sanitize_filename(name, expected):
    assert sanitize_filename(name) == expected
