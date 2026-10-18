import os
import sys
import json
import errno
import socket
import logging
import threading
import uvicorn
import mimetypes
import shutil
import tempfile
from pathlib import Path
from urllib.parse import quote, unquote
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.convertors import Convertor, register_url_convertor
from starlette.requests import ClientDisconnect

from src.access import CODE_ALPHABET, CODE_LENGTH, SESSION_COOKIE, TooManyTries, access, normalize_code
from src.config import config
from src.middleware import BrowserProtection
from src.paths import is_listable, resolve_in_root
from src.thumbs import thumb_for
from src.uploads import declared_length, has_room, sanitize_filename, save_upload
from src.zipstream import ZipStream, chunks_in_pool, in_pool, zip_stream

log = logging.getLogger(__name__)
executor = ThreadPoolExecutor(max_workers=4)
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(BrowserProtection)

MAX_LOGIN_BODY = 1024
VIEW_SANDBOX = "sandbox; default-src 'none'; img-src 'self'; media-src 'self'; style-src 'unsafe-inline'"
MAX_OPEN_FILES = 10240

# The running server, its thread and its socket
_running: tuple[uvicorn.Server, threading.Thread, socket.socket] | None = None
# The newest server thread, kept after stop_server so a late-ending one still blocks a new start
_last_thread: threading.Thread | None = None

class CodeConvertor(Convertor):
    """Matches one path segment that is the access code, in any case and with any dashes."""
    regex = f"-*(?:[{CODE_ALPHABET}{CODE_ALPHABET.lower()}]-*){{{CODE_LENGTH}}}"

    def convert(self, value: str) -> str:
        return normalize_code(value)

    def to_string(self, value: str) -> str:
        return value

register_url_convertor("access_code", CodeConvertor())

def require_session(request: Request):
    if access.require_code and not access.is_valid(request.cookies.get(SESSION_COOKIE)):
        raise HTTPException(401, "code_required")

def start_session(request: Request, code, response: Response) -> Response:
    """Puts a session cookie on response if code is right. Wrong codes count toward the client's limit."""
    try:
        token = access.try_code(request.client.host, code)
    except TooManyTries as e:
        raise HTTPException(429, "too_many_tries", {"Retry-After": str(e.retry_after)})
    if token is None:
        raise HTTPException(401, "wrong_code")
    response.set_cookie(SESSION_COOKIE, token, path="/", httponly=True, samesite="strict")
    return response

@app.post("/api/login")
async def login(request: Request):
    length = request.headers.get("content-length")
    if length is None: raise HTTPException(411)
    if not length.isdigit(): raise HTTPException(400)
    if int(length) > MAX_LOGIN_BODY: raise HTTPException(413)
    if not access.require_code: return Response(status_code=204)
    try:
        body = json.loads(await request.body())
    except ValueError:
        raise HTTPException(400)
    code = body.get("code") if isinstance(body, dict) else None
    return start_session(request, code, Response(status_code=204))

@app.post("/api/logout", dependencies=[Depends(require_session)])
async def logout(request: Request):
    access.end_session(request.cookies.get(SESSION_COOKIE))
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="strict")
    return response

# The file endpoints are plain def, so Starlette runs them, and their file-system work, off the event loop
@app.get("/api/files", dependencies=[Depends(require_session)])
def list_files(path: str = ""):
    req_path = resolve_in_root(path)
    if not req_path.is_dir(): raise HTTPException(404)
    root = Path(config.ROOT_DIR).resolve()
    
    items = []
    try:
        with os.scandir(req_path) as entries:
            for entry in entries:
                try:
                    entry_path = Path(entry.path)
                    if not is_listable(entry_path, root): continue
                    stat = entry.stat()
                    is_dir = entry.is_dir()
                    mime, _ = mimetypes.guess_type(entry.path)
                    items.append({
                        "name": entry.name,
                        "path": str(Path(path) / entry.name).replace("\\", "/"),
                        "is_dir": is_dir,
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                        "mime": mime,
                        "type": "folder" if is_dir else ("image" if mime and mime.startswith('image') else ("video" if mime and mime.startswith('video') else "file"))
                    })
                except: continue
    except PermissionError: raise HTTPException(403)
    except OSError: raise HTTPException(404)
    return items

@app.get("/api/thumb", dependencies=[Depends(require_session)])
def get_thumb(path: str):
    real_path = resolve_in_root(path)
    cache_dir = config.THUMB_CACHE_DIR
    if cache_dir is None: raise HTTPException(404)
    thumb = executor.submit(thumb_for, real_path, cache_dir).result()
    if thumb is None: raise HTTPException(404)
    return FileResponse(thumb)

@app.get("/api/download", dependencies=[Depends(require_session)])
def download_file(path: str):
    real_path = resolve_in_root(path)
    if real_path.is_file(): return FileResponse(real_path, filename=real_path.name)
    raise HTTPException(404)

@app.get("/api/download_folder", dependencies=[Depends(require_session)])
def download_folder(path: str):
    real_path = resolve_in_root(path)
    if not real_path.is_dir(): raise HTTPException(400)
    root = Path(config.ROOT_DIR).resolve()
    skip = config.THUMB_CACHE_DIR.resolve() if config.THUMB_CACHE_DIR else None
    stream = zip_stream(real_path, root, skip)
    if stream is None: raise HTTPException(503, headers={"Retry-After": "5"})
    return ZipResponse(stream, f"{real_path.name}.zip")

class ZipResponse(StreamingResponse):
    """A ZIP made in the ZIP pool. However the response ends, the ZIP stops and its slot is freed before this returns."""
    def __init__(self, stream: ZipStream, filename: str):
        super().__init__(chunks_in_pool(stream), media_type="application/zip",
                         headers={"Content-Disposition": attachment(filename)})
        self.stream = stream

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            await in_pool(self.stream.close)

def attachment(filename: str) -> str:
    """Content-Disposition in the same form as FileResponse's."""
    quoted = quote(filename)
    return f"attachment; filename*=utf-8''{quoted}" if quoted != filename else f'attachment; filename="{filename}"'

def renders_inline(mime: str | None) -> bool:
    """Images except SVG, video, audio, PDF and plain text. Anything else could run script."""
    if not mime: return False
    if mime.startswith("image/"): return mime != "image/svg+xml"
    return mime.startswith(("video/", "audio/")) or mime in ("application/pdf", "text/plain")

@app.get("/api/view", dependencies=[Depends(require_session)])
def view_media(path: str):
    real_path = resolve_in_root(path)
    if not real_path.is_file(): raise HTTPException(404)
    mime, _ = mimetypes.guess_type(real_path.name)
    if not renders_inline(mime): mime = "text/plain"
    # Browsers' PDF viewers refuse to render in a sandbox; nosniff and the viewer's own isolation cover PDFs
    headers = {} if mime == "application/pdf" else {"Content-Security-Policy": VIEW_SANDBOX}
    return FileResponse(real_path, media_type=mime, headers=headers)

@app.get("/api/server_info", dependencies=[Depends(require_session)])
async def server_info():
    return {"allow_upload": bool(config.ALLOW_UPLOAD), "require_code": access.require_code}

@app.post("/api/upload", dependencies=[Depends(require_session)])
async def upload_file(request: Request):
    # No body parameters, so nothing is read or spooled to disk before these checks
    if not config.ALLOW_UPLOAD: raise HTTPException(403)
    if not config.UPLOAD_DIR or not await run_in_threadpool(os.path.isdir, config.UPLOAD_DIR): raise HTTPException(503)
    length = declared_length(request.headers.get("content-length"))
    upload_dir = await run_in_threadpool(Path(config.UPLOAD_DIR).resolve)
    if not await run_in_threadpool(has_room, upload_dir, length): raise HTTPException(507)

    name = sanitize_filename(unquote(request.headers.get("x-file-name", "")))
    try:
        target_path = await save_upload(request.stream(), upload_dir, name, length)
    except ClientDisconnect:
        raise HTTPException(400)
    except OSError as e:
        log.exception("Upload failed")
        raise HTTPException(507 if e.errno == errno.ENOSPC else 500)

    rel_path = await run_in_threadpool(path_in_share, target_path)
    return JSONResponse({
        "name": target_path.name,
        "size": length,
        "path": rel_path,
        "saved_outside_root": rel_path is None,
    })

def path_in_share(path: Path) -> str | None:
    """path relative to the shared folder, or None if it's outside it."""
    try:
        return str(path.resolve().relative_to(Path(config.ROOT_DIR).resolve())).replace("\\", "/")
    except ValueError:
        return None

# Before the static mount. It only matches code-shaped segments, so static files (which have dots) still reach the mount
@app.get("/{code:access_code}", include_in_schema=False)
async def enter_with_code(code: str, request: Request):
    if not access.require_code: return RedirectResponse("/", 303)
    try:
        return start_session(request, code, RedirectResponse("/", 303))
    except HTTPException:
        # Wrong code or a wait (still counted): send an old QR code to the code screen rather than JSON
        return RedirectResponse("/", 303)

if os.path.exists(config.FRONTEND_DIST_DIR):
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIST_DIR, html=True), name="static")

def open_cache_dir() -> Path:
    """Makes this run's private thumbnail folder."""
    config.THUMB_CACHE_DIR = Path(tempfile.mkdtemp(prefix="RapydShare_"))
    return config.THUMB_CACHE_DIR

def close_cache_dir():
    if config.THUMB_CACHE_DIR is None: return
    shutil.rmtree(config.THUMB_CACHE_DIR, ignore_errors=True)
    config.THUMB_CACHE_DIR = None

def parse_port(text: str) -> int:
    """text as a port number from 1 to 65535. Raises ValueError for anything else."""
    text = text.strip()
    if not (text.isascii() and text.isdigit()) or not 1 <= int(text) <= 65535:
        raise ValueError("Port must be a number from 1 to 65535.")
    return int(text)

def open_listen_socket(port: int, host: str = "0.0.0.0") -> socket.socket:
    """Binds and listens now, so a port in use raises OSError here rather than in the server thread."""
    return socket.create_server((host, port))

def raise_file_limit():
    """macOS gives apps 256 open files by default, which browsers' connections and downloads can use up."""
    if sys.platform != "darwin": return
    import resource
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    target = min(MAX_OPEN_FILES, hard)
    if soft >= target: return
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
    except (ValueError, OSError):
        log.warning("Couldn't raise the open file limit", exc_info=True)

def start_server(sock: socket.socket) -> threading.Thread:
    """Serves the app on sock, from open_listen_socket, in a new thread. server_started() says when it's up.

    Raises RuntimeError if an earlier server's thread hasn't ended, or OSError if the cache folder can't be made. sock is closed then.
    """
    global _running, _last_thread
    try:
        if _last_thread is not None and _last_thread.is_alive():
            raise RuntimeError("The earlier server is still shutting down.")
        open_cache_dir()
    except Exception:
        sock.close()
        raise
    raise_file_limit()
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["handlers"]["default"]["stream"] = "ext://sys.stderr"
    log_config["handlers"]["access"]["stream"] = "ext://sys.stdout"
    # uvicorn can't time out a connection that never sends a request; keep-alive only drops idle ones after a response
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", log_config=log_config,
                                           timeout_keep_alive=5, timeout_graceful_shutdown=1))
    thread = threading.Thread(target=server.run, args=([sock],), daemon=True)
    _running = (server, thread, sock)
    _last_thread = thread
    thread.start()
    return thread

def server_started() -> bool:
    return _running is not None and _running[0].started

def stop_server(timeout: float = 3.0) -> bool:
    """Stops the server and waits up to timeout seconds for its thread, then ends access and removes the cache folder.

    True if the thread has ended. Safe to call when nothing is running.
    """
    global _running
    running, _running = _running, None
    ended = True
    if running:
        server, thread, sock = running
        server.should_exit = True
        thread.join(timeout)
        ended = not thread.is_alive()
        sock.close()  # uvicorn only closes it if it got as far as starting
    access.stop()
    close_cache_dir()
    return ended
