import ipaddress
import re
import socket

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

# A name or [IPv6 literal], then an optional port
HOST_PATTERN = re.compile(r"(\[([^\]]*)\]|[^:\[\]]*)(?::[0-9]+)?")


def own_local_name() -> str:
    """This machine's <name>.local, lowercase, whether or not gethostname() already ends in .local."""
    name = socket.gethostname().lower()
    return name if name.endswith(".local") else name + ".local"


def host_is_allowed(host: str) -> bool:
    """IP literals (v6 in brackets), localhost and this machine's <name>.local, with an optional port."""
    match = HOST_PATTERN.fullmatch(host.lower())
    if not match: return False
    name, ipv6 = match.group(1), match.group(2)
    if name in ("localhost", own_local_name()): return True
    try:
        address = ipaddress.ip_address(ipv6 or name)
    except ValueError:
        return False
    return address.version == (6 if ipv6 else 4)


def origin_is_allowed(scope, headers: Headers) -> bool:
    """Non-GET/HEAD requests with an Origin must come from this server's own scheme, host and port."""
    origin = headers.get("origin")
    if scope["method"] in ("GET", "HEAD") or origin is None: return True
    return origin.lower() == f"{scope['scheme']}://{headers.get('host', '')}".lower()


def add_security_headers(message, path: str):
    headers = MutableHeaders(scope=message)
    headers["X-Content-Type-Options"] = "nosniff"
    headers["Referrer-Policy"] = "no-referrer"
    # The web client shows previews in its own iframes
    frame, ancestors = ("SAMEORIGIN", "'self'") if path == "/api/view" else ("DENY", "'none'")
    headers["X-Frame-Options"] = frame
    csp = headers.get("Content-Security-Policy")
    headers["Content-Security-Policy"] = f"{csp}; frame-ancestors {ancestors}" if csp else f"frame-ancestors {ancestors}"
    if path.startswith("/api/"): headers["Cache-Control"] = "no-store"


class BrowserProtection:
    """Host allowlist (stops DNS rebinding), same-origin writes and security headers on every response."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                add_security_headers(message, scope["path"])
            await send(message)

        headers = Headers(scope=scope)
        if not host_is_allowed(headers.get("host", "")):
            return await JSONResponse({"detail": "bad_host"}, 400)(scope, receive, send_with_headers)
        if not origin_is_allowed(scope, headers):
            return await JSONResponse({"detail": "bad_origin"}, 403)(scope, receive, send_with_headers)
        await self.app(scope, receive, send_with_headers)
