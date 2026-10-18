import asyncio
import ctypes
import ctypes.util
import sys
import tempfile
import unicodedata
from urllib.parse import quote

import pytest

from src import uploads
from src.access import access
from src.config import config
from src.paths import is_hidden
from src.server import app

MB = 1024 * 1024


@pytest.fixture
def uploads_dir(share, monkeypatch):
    """Turns uploads on, into shared/uploads, and returns that folder."""
    folder = share / "uploads"
    folder.mkdir()
    monkeypatch.setattr(config, "ALLOW_UPLOAD", True)
    monkeypatch.setattr(config, "UPLOAD_DIR", str(folder))
    return folder


@pytest.fixture
def temp_dir(tmp_path, monkeypatch):
    """Points the system temp folder at an empty folder and returns it."""
    folder = tmp_path / "tmp"
    folder.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(folder))
    return folder


def encode_name(name):
    """What the client's encodeURIComponent does."""
    return quote(name, safe="-_.!~*'()")


def upload(client, filename, content=b"data"):
    return client.post("/api/upload", content=content, headers={
        "X-File-Name": encode_name(filename),
        "Content-Type": "application/octet-stream",
    })


def send_raw(headers, messages):
    """Sends an upload straight to the app, feeding it messages as the body.
    Returns the status, the response body and how many messages the app read."""
    messages = list(messages)
    read = 0
    sent = []

    async def receive():
        nonlocal read
        read += 1
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "POST", "scheme": "http", "path": "/api/upload", "raw_path": b"/api/upload",
        "root_path": "", "query_string": b"",
        "headers": [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers.items()],
        "client": ("127.0.0.1", 50000), "server": ("127.0.0.1", 8000),
    }
    asyncio.run(app(scope, receive, send))
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, body.decode(), read


def raw_headers(length, name="report.txt"):
    headers = {"host": "127.0.0.1:8000", "x-file-name": encode_name(name),
               "content-type": "application/octet-stream"}
    if length is not None:
        headers["content-length"] = str(length)
    return headers


def body_messages(*chunks):
    return [{"type": "http.request", "body": c, "more_body": i < len(chunks) - 1} for i, c in enumerate(chunks)]


def assert_no_paths(text, *folders):
    for folder in folders:
        assert str(folder) not in text
        assert folder.name not in text


# --- The gate ---

def test_the_route_reads_no_body_itself():
    route = next(r for r in app.routes if getattr(r, "path", None) == "/api/upload")
    assert route.body_field is None


@pytest.mark.parametrize("case,expected", [
    ("no_session", 401),
    ("uploads_off", 403),
    ("no_upload_dir", 503),
    ("upload_dir_missing", 503),
    ("no_length", 411),
    ("bad_length", 400),
    ("over_limit", 413),
    ("disk_full", 507),
])
def test_rejected_before_reading_or_writing_anything(share, uploads_dir, temp_dir, monkeypatch, case, expected):
    big = b"x" * (2 * MB)
    length = len(big)
    if case == "no_session":
        access.start(require_code=True)
    elif case == "uploads_off":
        monkeypatch.setattr(config, "ALLOW_UPLOAD", False)
    elif case == "no_upload_dir":
        monkeypatch.setattr(config, "UPLOAD_DIR", "")
    elif case == "upload_dir_missing":
        monkeypatch.setattr(config, "UPLOAD_DIR", str(uploads_dir / "gone"))
    elif case == "no_length":
        length = None
    elif case == "bad_length":
        length = "12abc"
    elif case == "over_limit":
        length = 20 * 1024 ** 3 + 1
    elif case == "disk_full":
        monkeypatch.setattr(uploads, "MIN_FREE_BYTES", 2 ** 62)

    status, body, read = send_raw(raw_headers(length), body_messages(big))

    assert status == expected
    assert read == 0
    assert list(uploads_dir.iterdir()) == []
    assert list(temp_dir.iterdir()) == []
    assert_no_paths(body, uploads_dir, share)


def test_the_limits():
    assert uploads.MAX_UPLOAD_BYTES == 20 * 1024 ** 3
    assert uploads.MIN_FREE_BYTES == 1024 ** 3


def test_streams_into_the_upload_folder_not_the_temp_folder(client, uploads_dir, temp_dir):
    big = b"x" * (2 * MB)
    r = upload(client, "big.bin", big)
    assert r.status_code == 200
    assert (uploads_dir / "big.bin").read_bytes() == big
    assert list(temp_dir.iterdir()) == []


# --- Behaviour kept from before ---

def test_refused_when_uploads_are_off(client, share):
    r = upload(client, "report.txt")
    assert r.status_code == 403
    assert not (share / "report.txt").exists()


def test_saves_the_file(client, uploads_dir):
    r = upload(client, "report.txt", b"quarterly numbers")
    assert r.status_code == 200
    assert (uploads_dir / "report.txt").read_bytes() == b"quarterly numbers"
    assert r.json() == {
        "name": "report.txt",
        "size": 17,
        "path": "uploads/report.txt",
        "saved_outside_root": False,
    }


def test_saves_an_empty_file(client, uploads_dir):
    r = upload(client, "empty.txt", b"")
    assert r.status_code == 200
    assert (uploads_dir / "empty.txt").read_bytes() == b""


def test_never_overwrites_an_existing_file(client, uploads_dir):
    names = [upload(client, "report.txt", body).json()["name"] for body in (b"one", b"two", b"three")]
    assert names == ["report.txt", "report (1).txt", "report (2).txt"]
    assert (uploads_dir / "report.txt").read_bytes() == b"one"
    assert (uploads_dir / "report (2).txt").read_bytes() == b"three"


def test_numbers_files_without_an_extension(client, uploads_dir):
    upload(client, "README")
    assert upload(client, "README").json()["name"] == "README (1)"


@pytest.mark.parametrize("filename", [
    "../../escaped.txt",
    "..\\..\\escaped.txt",
    "/tmp/escaped.txt",
])
def test_paths_in_the_filename_are_dropped(client, uploads_dir, filename):
    r = upload(client, filename)
    assert r.status_code == 200
    assert r.json()["name"] == "escaped.txt"
    assert (uploads_dir / "escaped.txt").exists()
    assert not (uploads_dir.parent.parent / "escaped.txt").exists()


def test_reports_uploads_outside_the_shared_folder(client, share, monkeypatch, tmp_path):
    outside = tmp_path / "inbox"
    outside.mkdir()
    monkeypatch.setattr(config, "ALLOW_UPLOAD", True)
    monkeypatch.setattr(config, "UPLOAD_DIR", str(outside))

    r = upload(client, "report.txt")
    assert r.status_code == 200
    assert (outside / "report.txt").exists()
    assert r.json()["path"] is None
    assert r.json()["saved_outside_root"] is True


# --- Names ---

@pytest.mark.parametrize("filename", ["résumé 🎉.txt", "写真.jpg", "Ünïcödé.pdf"])
def test_non_ascii_and_emoji_names_round_trip(client, uploads_dir, filename):
    r = upload(client, filename)
    assert r.status_code == 200
    assert r.json()["name"] == filename
    assert r.json()["path"] == f"uploads/{filename}"
    assert (uploads_dir / filename).read_bytes() == b"data"


def test_decomposed_names_are_saved_composed(client, uploads_dir):
    r = upload(client, unicodedata.normalize("NFD", "résumé.txt"))
    assert r.json()["name"] == "résumé.txt"
    assert [p.name for p in uploads_dir.iterdir()] == ["résumé.txt"]


def test_a_missing_name_is_saved_as_unnamed(client, uploads_dir):
    r = client.post("/api/upload", content=b"data", headers={"Content-Type": "application/octet-stream"})
    assert r.json()["name"] == "unnamed"


def test_risky_types_are_renamed(client, uploads_dir):
    assert upload(client, "site.url").json()["name"] == "site.url.txt"
    assert (uploads_dir / "site.url.txt").exists()
    assert not (uploads_dir / "site.url").exists()


# --- Writing ---

async def interleaved_uploads(folder, count):
    """Starts count uploads of report.txt and holds each one mid-body until all of them have started."""
    started = 0
    all_started = asyncio.Event()

    async def body(i):
        nonlocal started
        yield f"upload {i} ".encode()
        started += 1
        if started == count:
            all_started.set()
        await all_started.wait()
        yield b"end"

    return await asyncio.gather(*(
        uploads.save_upload(body(i), folder, "report.txt", len(f"upload {i} end"))
        for i in range(count)))


def test_concurrent_same_name_uploads_never_overwrite_each_other(uploads_dir):
    saved = asyncio.run(interleaved_uploads(uploads_dir, 5))

    assert sorted(p.name for p in saved) == sorted(
        ["report.txt"] + [f"report ({i}).txt" for i in range(1, 5)])
    assert sorted(p.read_bytes() for p in saved) == sorted(f"upload {i} end".encode() for i in range(5))
    assert sorted(p.name for p in uploads_dir.iterdir()) == sorted(p.name for p in saved)


def test_the_partial_file_is_hidden_and_not_served(client, uploads_dir):
    seen = []

    async def body():
        yield b"first half"
        seen.extend(uploads_dir.iterdir())
        seen.append(client.get("/api/download", params={"path": f"uploads/{seen[0].name}"}).status_code)
        yield b"second half"

    saved = asyncio.run(uploads.save_upload(body(), uploads_dir, "report.txt", 21))

    part, status = seen
    assert part.name == ".report.txt.part"
    assert is_hidden(part)
    assert status == 404
    assert [p.name for p in uploads_dir.iterdir()] == [saved.name]


def test_an_aborted_upload_leaves_nothing_behind(share, uploads_dir):
    # The client goes away after the first chunk
    status, body, _ = send_raw(raw_headers(3 * MB), [{"type": "http.request", "body": b"x" * MB, "more_body": True}])
    assert status == 400
    assert list(uploads_dir.iterdir()) == []
    assert_no_paths(body, uploads_dir, share)


def test_a_body_shorter_than_declared_leaves_nothing_behind(share, uploads_dir):
    status, body, _ = send_raw(raw_headers(100), body_messages(b"short"))
    assert status == 400
    assert list(uploads_dir.iterdir()) == []
    assert_no_paths(body, uploads_dir, share)


def test_a_body_longer_than_declared_is_stopped(share, uploads_dir):
    status, body, _ = send_raw(raw_headers(5), body_messages(b"12345", b"6789"))
    assert status == 400
    assert list(uploads_dir.iterdir()) == []
    assert_no_paths(body, uploads_dir, share)


def test_a_failed_move_leaves_no_part_and_no_placeholder(client, share, uploads_dir, monkeypatch):
    def failing_replace(src, dst):
        raise OSError(f"cannot move {src} to {dst}")
    monkeypatch.setattr(uploads.os, "replace", failing_replace)

    r = upload(client, "report.txt")
    assert r.status_code == 500
    assert list(uploads_dir.iterdir()) == []
    assert_no_paths(r.text, uploads_dir, share)


def test_a_failure_mid_body_leaves_nothing_behind(uploads_dir):
    async def body():
        yield b"first half"
        raise OSError("read failed")

    with pytest.raises(OSError):
        asyncio.run(uploads.save_upload(body(), uploads_dir, "report.txt", 21))
    assert list(uploads_dir.iterdir()) == []


def test_stops_and_cleans_up_when_the_disk_fills_during_the_upload(share, uploads_dir, monkeypatch):
    reports = iter([2 ** 62, 0])  # Plenty at the gate, then none
    monkeypatch.setattr(uploads, "free_space", lambda folder: next(reports, 0))
    monkeypatch.setattr(uploads, "CHECK_FREE_EVERY", MB)

    status, body, _ = send_raw(raw_headers(3 * MB), body_messages(b"x" * MB, b"y" * MB, b"z" * MB))
    assert status == 507
    assert list(uploads_dir.iterdir()) == []
    assert_no_paths(body, uploads_dir, share)


# --- Marked as downloaded ---

def read_xattr(path, name):
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    libc.getxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p,
                              ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
    libc.getxattr.restype = ctypes.c_ssize_t
    buf = ctypes.create_string_buffer(1024)
    size = libc.getxattr(str(path).encode(), name.encode(), buf, 1024, 0, 0)
    return buf.raw[:size].decode() if size >= 0 else None


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS quarantine")
def test_saved_uploads_are_quarantined_on_macos(client, uploads_dir):
    upload(client, "report.txt")
    value = read_xattr(uploads_dir / "report.txt", "com.apple.quarantine")
    assert value is not None
    assert value.split(";")[2] == "RapydShare"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Mark of the Web")
def test_saved_uploads_get_a_zone_identifier_on_windows(client, uploads_dir):
    upload(client, "report.txt")
    with open(str(uploads_dir / "report.txt") + ":Zone.Identifier", "rb") as f:
        assert f.read() == b"[ZoneTransfer]\r\nZoneId=3"
