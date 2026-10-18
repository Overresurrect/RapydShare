import socket

import pytest

from src.config import config

SANDBOX = "sandbox; default-src 'none'; img-src 'self'; media-src 'self'; style-src 'unsafe-inline'"


def info(client, host):
    return client.get("/api/server_info", headers={"host": host})


# --- Host allowlist (DNS rebinding) ---

@pytest.mark.parametrize("host", [
    "127.0.0.1", "127.0.0.1:8000", "192.168.1.20:8000", "[::1]", "[::1]:8000",
    "[fe80::1]:8000", "localhost", "localhost:8000", "LOCALHOST:8000",
])
def test_allowed_hosts(client, host):
    assert info(client, host).status_code == 200


@pytest.mark.parametrize("host", [
    "evil.com", "evil.com:8000", "127.0.0.1.evil.com", "localhost.evil.com", "other.local",
    "::1", "[::1", "[::1]x", "127.0.0.1:", "127.0.0.1:80x", "999.1.1.1", "", "localhost:8000:1",
])
def test_other_hosts_are_400(client, host):
    r = info(client, host)
    assert r.status_code == 400
    assert r.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("hostname", ["Aayushs-MacBook-Pro.local", "Aayushs-MacBook-Pro", "AAYUSHS-MACBOOK-PRO.LOCAL"])
@pytest.mark.parametrize("host", ["aayushs-macbook-pro.local", "Aayushs-MacBook-Pro.local:8000", "AAYUSHS-MACBOOK-PRO.LOCAL"])
def test_own_local_name_is_allowed_in_any_case(client, monkeypatch, hostname, host):
    monkeypatch.setattr(socket, "gethostname", lambda: hostname)
    assert info(client, host).status_code == 200


@pytest.mark.parametrize("host", ["aayushs-macbook-pro", "aayushs-macbook-pro.local.local", "other-mac.local"])
def test_other_names_are_400(client, monkeypatch, host):
    monkeypatch.setattr(socket, "gethostname", lambda: "Aayushs-MacBook-Pro.local")
    assert info(client, host).status_code == 400


@pytest.fixture
def uploads_on(share, tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(config, "ALLOW_UPLOAD", True)
    monkeypatch.setattr(config, "UPLOAD_DIR", str(uploads))
    return uploads


# --- Origin check ---

POSTS = [
    ("/api/login", {"json": {"code": "ABCDEF"}}),
    ("/api/logout", {}),
    ("/api/upload", {"content": b"x", "headers": {"x-file-name": "a.txt"}}),
]


@pytest.mark.parametrize("origin", ["http://evil.com", "http://127.0.0.1:9000", "https://127.0.0.1:8000", "null"])
@pytest.mark.parametrize("path, kwargs", POSTS, ids=[p for p, _ in POSTS])
def test_cross_origin_post_is_403(client, uploads_on, path, kwargs, origin):
    headers = {**kwargs.get("headers", {}), "origin": origin}
    r = client.post(path, **{**kwargs, "headers": headers})
    assert r.status_code == 403


def test_same_origin_post_is_allowed(client):
    assert client.post("/api/login", json={"code": "ABCDEF"}, headers={"origin": "http://127.0.0.1:8000"}).status_code == 204


def test_post_without_origin_is_allowed(client):
    assert client.post("/api/login", json={"code": "ABCDEF"}).status_code == 204


def test_same_origin_is_matched_in_any_case(client):
    r = client.post("/api/login", json={"code": "ABCDEF"},
                    headers={"host": "LOCALHOST:8000", "origin": "http://localhost:8000"})
    assert r.status_code == 204


def test_get_ignores_origin(client):
    assert client.get("/api/server_info", headers={"origin": "http://evil.com"}).status_code == 200


# --- Headers on every response ---

def test_security_headers_on_api(client):
    r = client.get("/api/server_info")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["content-security-policy"] == "frame-ancestors 'none'"
    assert r.headers["cache-control"] == "no-store"


def test_security_headers_on_errors(client, code_on):
    r = client.get("/api/files")
    assert r.status_code == 401
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"


def test_non_api_responses_deny_framing_without_no_store(client):
    r = client.get("/no-such-page.html")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["content-security-policy"] == "frame-ancestors 'none'"
    assert "cache-control" not in r.headers


def test_view_allows_same_origin_framing(client):
    r = client.get("/api/view", params={"path": "photo.png"})
    assert r.status_code == 200
    assert r.headers["x-frame-options"] == "SAMEORIGIN"
    assert r.headers["content-security-policy"] == SANDBOX + "; frame-ancestors 'self'"
    assert r.headers["cache-control"] == "no-store"


def test_view_error_allows_same_origin_framing(client):
    r = client.get("/api/view", params={"path": "missing.png"})
    assert r.status_code == 404
    assert r.headers["x-frame-options"] == "SAMEORIGIN"
    assert r.headers["content-security-policy"] == "frame-ancestors 'self'"


# --- /api/view content types ---

@pytest.mark.parametrize("name", ["page.html", "page.HTM", "image.svg", "data.xml", "page.xhtml", "blob.unknownext"])
def test_risky_types_are_plain_text_in_a_sandbox(client, share, name):
    (share / name).write_text("<script>alert(1)</script>")
    r = client.get("/api/view", params={"path": name})
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/plain; charset=utf-8"
    assert r.headers["content-security-policy"] == SANDBOX + "; frame-ancestors 'self'"
    assert r.text == "<script>alert(1)</script>"


@pytest.mark.parametrize("name, mime", [
    ("photo.png", "image/png"), ("clip.mp4", "video/mp4"), ("song.mp3", "audio/mpeg"),
    ("hello.txt", "text/plain; charset=utf-8"),
])
def test_safe_types_keep_their_type_in_a_sandbox(client, share, name, mime):
    if not (share / name).exists():
        (share / name).write_bytes(b"\x00" * 16)
    r = client.get("/api/view", params={"path": name})
    assert r.headers["content-type"] == mime
    assert r.headers["content-security-policy"].startswith("sandbox;")


def test_pdf_has_no_sandbox(client, share):
    (share / "doc.pdf").write_bytes(b"%PDF-1.4\n")
    r = client.get("/api/view", params={"path": "doc.pdf"})
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-security-policy"] == "frame-ancestors 'self'"
    assert r.headers["x-frame-options"] == "SAMEORIGIN"


def test_video_range_request_is_206(client, share):
    (share / "clip.mp4").write_bytes(bytes(range(100)))
    r = client.get("/api/view", params={"path": "clip.mp4"}, headers={"range": "bytes=10-19"})
    assert r.status_code == 206
    assert r.content == bytes(range(10, 20))
    assert r.headers["content-type"] == "video/mp4"
    assert r.headers["x-frame-options"] == "SAMEORIGIN"


# --- Docs pages off ---

@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_docs_pages_are_404(client, path):
    assert client.get(path).status_code == 404


def test_same_origin_upload_still_works(client, uploads_on):
    r = client.post("/api/upload", content=b"abc", headers={"x-file-name": "a.txt", "origin": "http://127.0.0.1:8000"})
    assert r.status_code == 200
    assert (uploads_on / "a.txt").read_bytes() == b"abc"
