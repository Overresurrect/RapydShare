from pathlib import Path

import pytest
from fastapi import HTTPException

from src.paths import path_text_is_safe, resolve_in_root

UNSAFE = [
    "a\x00b",              # NUL
    "a:b",                 # colon
    "hello.txt:secret",    # NTFS alternate data stream
    "C:x",                 # drive-relative
    "C:\\x",               # drive-absolute
    "C:/x",
    "\\\\host\\share",     # UNC
    "//host/share",        # UNC with forward slashes
    "\\\\?\\C:\\x",        # device path
    "\\\\.\\COM1",         # device namespace
    "/etc/passwd",         # leading slash
    "\\x",                 # leading backslash
]

SAFE = [
    "",
    "hello.txt",
    "docs/notes.txt",
    "docs\\notes.txt",
    "docs/../hello.txt",
    "..",
    "a b/c d.txt",
]


@pytest.mark.parametrize("path", UNSAFE)
def test_unsafe_text_is_refused(path):
    assert not path_text_is_safe(path)


@pytest.mark.parametrize("path", SAFE)
def test_relative_text_is_allowed(path):
    assert path_text_is_safe(path)


@pytest.fixture
def no_file_system(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("touched the file system")

    monkeypatch.setattr(Path, "resolve", boom)
    monkeypatch.setattr(Path, "stat", boom)


@pytest.mark.parametrize("path", UNSAFE)
def test_unsafe_text_is_refused_before_any_file_system_call(share, no_file_system, path):
    with pytest.raises(HTTPException) as e:
        resolve_in_root(path)
    assert e.value.status_code == 403
