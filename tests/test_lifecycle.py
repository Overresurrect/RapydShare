import asyncio
import http.client
import inspect
import json
import socket
import sys
import time

import pytest

from src import uploads
from src.access import access
from src.config import config
from src.server import app, open_listen_socket, parse_port, server_started, start_server, stop_server

FILE_ENDPOINTS = ["/api/files", "/api/thumb", "/api/download", "/api/download_folder", "/api/view"]


def start_on_free_port():
    """A real server on 127.0.0.1. Returns its port and thread once it has started."""
    sock = open_listen_socket(0, host="127.0.0.1")
    port = sock.getsockname()[1]
    thread = start_server(sock)
    deadline = time.monotonic() + 5
    while not server_started():
        assert thread.is_alive() and time.monotonic() < deadline, "the server didn't start"
        time.sleep(0.02)
    return port, thread


@pytest.fixture
def running(share):
    port, thread = start_on_free_port()
    yield port, thread
    stop_server()


def get(port, path):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", path)
    response = conn.getresponse()
    return conn, response


# --- Port ---

@pytest.mark.parametrize("text,port", [("1", 1), ("8000", 8000), (" 8080 ", 8080), ("65535", 65535)])
def test_parse_port_accepts_1_to_65535(text, port):
    assert parse_port(text) == port


@pytest.mark.parametrize("text", ["", "0", "65536", "99999", "-1", "+80", "80.0", "abc", "8 000", "٨٠", "0x50"])
def test_parse_port_rejects_everything_else(text):
    with pytest.raises(ValueError):
        parse_port(text)


def test_binding_a_port_in_use_raises_oserror():
    taken = socket.create_server(("127.0.0.1", 0))
    try:
        with pytest.raises(OSError):
            open_listen_socket(taken.getsockname()[1], host="127.0.0.1")
    finally:
        taken.close()


# --- A real server ---

def test_a_real_server_starts_and_serves(running):
    port, thread = running
    conn, response = get(port, "/api/files")
    try:
        assert response.status == 200
        assert "hello.txt" in {item["name"] for item in json.loads(response.read())}
    finally:
        conn.close()


def test_stop_returns_quickly_during_a_slow_download(share, running):
    port, thread = running
    with open(share / "big.bin", "wb") as f:
        f.truncate(256 * 1024 * 1024)
    conn, response = get(port, "/api/download?path=big.bin")
    try:
        assert response.status == 200
        response.read(1024)  # Then reads nothing more, so the server is left waiting to send

        started = time.monotonic()
        assert stop_server() is True
        assert time.monotonic() - started < 3.5
        assert not thread.is_alive()
    finally:
        conn.close()


def test_stop_ends_access_and_removes_the_cache_folder(running):
    port, thread = running
    access.start(require_code=True)
    cache = config.THUMB_CACHE_DIR
    assert cache.is_dir()

    assert stop_server() is True

    assert not server_started()
    assert access.code is None
    assert config.THUMB_CACHE_DIR is None
    assert not cache.exists()
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1).close()


def test_stop_without_a_server_is_harmless():
    assert stop_server() is True


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")
def test_starting_raises_the_open_file_limit_on_macos(share):
    import resource
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    resource.setrlimit(resource.RLIMIT_NOFILE, (256, hard))
    try:
        start_on_free_port()
        assert resource.getrlimit(resource.RLIMIT_NOFILE)[0] == min(10240, hard)
    finally:
        stop_server()
        resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))


# --- No stalls ---

@pytest.mark.parametrize("path", FILE_ENDPOINTS)
def test_file_endpoints_are_plain_def(path):
    route = next(r for r in app.routes if getattr(r, "path", None) == path)
    assert not inspect.iscoroutinefunction(route.endpoint)


def test_upload_file_system_work_runs_off_the_event_loop(client, share, monkeypatch):
    folder = share / "uploads"
    folder.mkdir()
    monkeypatch.setattr(config, "ALLOW_UPLOAD", True)
    monkeypatch.setattr(config, "UPLOAD_DIR", str(folder))
    on_loop = {}

    def watch(module, name):
        real = getattr(module, name)

        def watched(*args):
            try:
                asyncio.get_running_loop()
                on_loop[name] = True
            except RuntimeError:
                on_loop.setdefault(name, False)
            return real(*args)

        monkeypatch.setattr(module, name, watched)

    for name in ("has_room", "_move_into_place", "mark_downloaded"):
        watch(uploads, name)
    monkeypatch.setattr(uploads, "CHECK_FREE_EVERY", 1)  # So the check during the upload runs too
    monkeypatch.setattr("src.server.has_room", uploads.has_room)

    r = client.post("/api/upload", content=b"data", headers={
        "X-File-Name": "a.txt", "Content-Type": "application/octet-stream"})

    assert r.status_code == 200
    assert on_loop == {"has_room": False, "_move_into_place": False, "mark_downloaded": False}


# --- Starting twice, and failing to start ---

def test_starting_while_a_server_is_running_is_refused_and_closes_the_socket(running):
    extra = open_listen_socket(0, host="127.0.0.1")
    with pytest.raises(RuntimeError):
        start_server(extra)
    assert extra.fileno() == -1


def test_starting_while_a_stopped_server_has_not_ended_is_refused(share, monkeypatch):
    class Lingering:
        def is_alive(self):
            return True

    monkeypatch.setattr("src.server._last_thread", Lingering())
    extra = open_listen_socket(0, host="127.0.0.1")
    with pytest.raises(RuntimeError):
        start_server(extra)
    assert extra.fileno() == -1


def test_a_failure_making_the_cache_folder_closes_the_socket(share, monkeypatch):
    def fail():
        raise OSError("disk full")

    monkeypatch.setattr("src.server.open_cache_dir", fail)
    sock = open_listen_socket(0, host="127.0.0.1")
    with pytest.raises(OSError):
        start_server(sock)
    assert sock.fileno() == -1
    assert not server_started()
