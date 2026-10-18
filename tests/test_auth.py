import pytest
from fastapi.routing import APIRoute

from src.config import config
from src.server import app

# Every API route, so a new endpoint is covered as soon as it's added
API_ROUTES = sorted(
    (method, route.path)
    for route in app.routes if isinstance(route, APIRoute)
    for method in route.methods
)


@pytest.fixture
def auth_on(share, monkeypatch):
    monkeypatch.setattr(config, "USE_AUTH", True)


def test_open_without_auth(client):
    assert client.get("/api/server_info").status_code == 200


@pytest.mark.parametrize("method,path", API_ROUTES, ids=[f"{m} {p}" for m, p in API_ROUTES])
def test_every_api_route_needs_credentials(client, auth_on, method, path):
    r = client.request(method, path, params={"path": "hello.txt"})
    assert r.status_code == 401
    # Without this header the browser never shows its login prompt
    assert r.headers["www-authenticate"] == "Basic"


@pytest.mark.parametrize("username,password", [
    ("admin", "wrong"),
    ("someone", "1234"),
    ("", ""),
])
def test_wrong_credentials_are_refused(client, auth_on, username, password):
    assert client.get("/api/server_info", auth=(username, password)).status_code == 401


def test_right_credentials_are_accepted(client, auth_on):
    r = client.get("/api/download", params={"path": "hello.txt"}, auth=("admin", "1234"))
    assert r.status_code == 200
    assert r.content == b"hello"
