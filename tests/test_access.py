import pytest
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from starlette.routing import Mount

from src.access import SESSION_COOKIE, access
from src.server import app

# Every API route, so a new endpoint is covered as soon as it's added
API_ROUTES = sorted(
    (method, route.path)
    for route in app.routes if isinstance(route, APIRoute) and route.path.startswith("/api/")
    for method in route.methods
)
SESSION_ROUTES = [(m, p) for m, p in API_ROUTES if p != "/api/login"]


def wrong_code(code):
    return "222222" if code != "222222" else "333333"


def login(client, code):
    return client.post("/api/login", json={"code": code})


def assert_session_cookie(r):
    name, _, rest = r.headers["set-cookie"].partition("=")
    assert name == SESSION_COOKIE
    token, *attrs = rest.split(";")
    assert len(token) >= 43  # 32 random bytes
    attrs = {a.strip().lower() for a in attrs}
    assert {"httponly", "samesite=strict", "path=/"} <= attrs
    # No lifetime: the cookie ends when the browser closes
    assert not any(a.startswith(("max-age", "expires")) for a in attrs)


def files_status(client):
    return client.get("/api/files").status_code


# --- Every API route needs a session ---

@pytest.mark.parametrize("method,path", SESSION_ROUTES, ids=[f"{m} {p}" for m, p in SESSION_ROUTES])
def test_every_api_route_needs_a_session(client, code_on, method, path):
    r = client.request(method, path, params={"path": "hello.txt"})
    assert r.status_code == 401
    assert r.json() == {"detail": "code_required"}
    assert "www-authenticate" not in r.headers


def test_a_made_up_session_is_refused(client, code_on):
    client.cookies.set(SESSION_COOKIE, "x" * 43)
    assert files_status(client) == 401


def test_no_basic_auth_left(client, code_on):
    assert client.get("/api/files", auth=("admin", "password")).status_code == 401


def test_code_off_opens_the_routes(client):
    r = client.get("/api/download", params={"path": "hello.txt"})
    assert r.status_code == 200
    assert r.content == b"hello"


def test_server_info(client, code_on):
    login(client, code_on)
    assert client.get("/api/server_info").json() == {"allow_upload": False, "require_code": True}


def test_server_info_with_code_off(client):
    assert client.get("/api/server_info").json() == {"allow_upload": False, "require_code": False}


# --- The code in the address ---

def test_code_url_sets_the_cookie_and_redirects(client, code_on):
    r = client.get(f"/{code_on}", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    assert_session_cookie(r)
    assert files_status(client) == 200


@pytest.mark.parametrize("shape", [str.lower, lambda c: f"{c[:3]}-{c[3:]}", lambda c: f"{c[:3].lower()}-{c[3:]}-"])
def test_code_url_ignores_case_and_dash(client, code_on, shape):
    r = client.get(f"/{shape(code_on)}", follow_redirects=False)
    assert r.status_code == 303
    assert files_status(client) == 200


def assert_sent_to_code_screen(r):
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    assert "set-cookie" not in r.headers


def test_wrong_code_url_goes_to_the_code_screen(client, code_on):
    # An old QR code lands on the code-entry screen, not raw JSON
    assert_sent_to_code_screen(client.get(f"/{wrong_code(code_on)}", follow_redirects=False))
    assert files_status(client) == 401


def test_code_url_during_a_wait_goes_to_the_code_screen(client, code_on):
    for _ in range(5):
        login(client, wrong_code(code_on))
    assert_sent_to_code_screen(client.get(f"/{code_on}", follow_redirects=False))
    assert files_status(client) == 401


def test_wrong_code_urls_count_toward_the_limit(client, code_on):
    for _ in range(5):
        assert_sent_to_code_screen(client.get(f"/{wrong_code(code_on)}", follow_redirects=False))
    r = login(client, code_on)
    assert r.status_code == 429
    assert r.headers["retry-after"] == "2"


@pytest.mark.parametrize("path", ["/ABCDE", "/ABCDEFG", "/ABCDE0", "/abcdeo", "/ABC/DEF", "/ABCDEF.txt", "/api"])
def test_only_code_shaped_segments_reach_the_code_route(client, code_on, path):
    for _ in range(6):
        assert client.get(path, follow_redirects=False).status_code == 404
    # None of them counted as a wrong code
    assert client.get(f"/{code_on}", follow_redirects=False).status_code == 303


def test_code_route_does_not_shadow_static_files(client, code_on, tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>client</html>")
    (dist / "vite.svg").write_text("<svg/>")
    (dist / "Rapydshare.ico").write_bytes(b"icon")
    (dist / "assets" / "index-AB12.js").write_text("js")
    mount = Mount("/", StaticFiles(directory=dist, html=True), name="static")
    # Drop any real bundle mounted at import (when frontend/dist exists) so the temporary one is what gets served
    routes = [r for r in app.router.routes if not (isinstance(r, Mount) and r.name == "static")]
    monkeypatch.setattr(app.router, "routes", [*routes, mount])

    assert client.get("/").text == "<html>client</html>"
    assert client.get("/vite.svg").text == "<svg/>"
    assert client.get("/Rapydshare.ico").content == b"icon"
    assert client.get("/assets/index-AB12.js").text == "js"
    assert client.get(f"/{code_on}", follow_redirects=False).status_code == 303


def test_code_url_with_code_off_just_redirects(client, monkeypatch):
    monkeypatch.setattr(access, "try_code", lambda *a: pytest.fail("counted a try with the code off"))
    r = client.get("/K7M2X9", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    assert "set-cookie" not in r.headers


# --- The login API ---

def test_login_sets_the_cookie(client, code_on):
    r = login(client, code_on)
    assert r.status_code == 204
    assert_session_cookie(r)
    assert files_status(client) == 200


def test_login_ignores_case_dash_and_space(client, code_on):
    assert login(client, f" {code_on[:3].lower()}-{code_on[3:]} ").status_code == 204


@pytest.mark.parametrize("body", [
    lambda c: {"code": wrong_code(c)},
    lambda c: {"code": c[:5]},
    lambda c: {"code": ""},
    lambda c: {"code": 123456},
    lambda c: {},
    lambda c: [c],
], ids=["wrong", "short", "empty", "number", "missing", "not an object"])
def test_login_refuses_wrong_codes(client, code_on, body):
    r = client.post("/api/login", json=body(code_on))
    assert r.status_code == 401
    assert r.json() == {"detail": "wrong_code"}
    assert "set-cookie" not in r.headers
    assert files_status(client) == 401


def test_login_waits_after_five_wrong_codes(client, code_on):
    for _ in range(5):
        assert login(client, wrong_code(code_on)).status_code == 401
    r = login(client, code_on)
    assert r.status_code == 429
    assert r.headers["retry-after"] == "2"
    assert "set-cookie" not in r.headers


def test_login_and_code_url_share_the_count(client, code_on):
    for _ in range(3):
        client.get(f"/{wrong_code(code_on)}", follow_redirects=False)
    for _ in range(2):
        login(client, wrong_code(code_on))
    assert login(client, code_on).status_code == 429


def test_login_needs_a_content_length(client, code_on):
    r = client.post("/api/login", content=iter([b'{"code": "%s"}' % code_on.encode()]))
    assert r.status_code == 411
    assert files_status(client) == 401


def test_login_refuses_a_large_body(client, code_on):
    body = b'{"code": "%s", "pad": "%s"}' % (code_on.encode(), b"x" * 1024)
    r = client.post("/api/login", content=body, headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    assert files_status(client) == 401


def test_login_refuses_a_body_that_is_not_json(client, code_on):
    r = client.post("/api/login", content=b"code=" + code_on.encode())
    assert r.status_code == 400
    assert files_status(client) == 401


def test_login_with_code_off(client, monkeypatch):
    monkeypatch.setattr(access, "try_code", lambda *a: pytest.fail("counted a try with the code off"))
    r = login(client, "K7M2X9")
    assert r.status_code == 204
    assert "set-cookie" not in r.headers


# --- Ending access ---

def test_logout_ends_the_session(client, code_on):
    login(client, code_on)
    token = client.cookies[SESSION_COOKIE]
    r = client.post("/api/logout")
    assert r.status_code == 204
    assert files_status(client) == 401
    # The old token no longer works, even if a client keeps sending it
    client.cookies.set(SESSION_COOKIE, token)
    assert files_status(client) == 401


def test_logout_ends_only_that_session(client, code_on):
    login(client, code_on)
    other = client.cookies[SESSION_COOKIE]
    client.cookies.clear()
    login(client, code_on)
    client.post("/api/logout")
    client.cookies.set(SESSION_COOKIE, other)
    assert files_status(client) == 200


def test_stop_ends_all_sessions(client, code_on):
    login(client, code_on)
    access.stop()
    assert files_status(client) == 401
    assert login(client, code_on).status_code == 401
