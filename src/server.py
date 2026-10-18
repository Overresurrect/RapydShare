import os
import re
import json
import uvicorn
import mimetypes
import shutil
import asyncio
import uuid
import aiofiles
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException, Depends, Request, Response, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from starlette.convertors import Convertor, register_url_convertor

from src.access import CODE_ALPHABET, CODE_LENGTH, SESSION_COOKIE, TooManyTries, access, normalize_code
from src.config import config
from src.paths import is_listable, resolve_in_root
from src.utils import generate_thumbnail

executor = ThreadPoolExecutor(max_workers=4)
app = FastAPI()

MAX_LOGIN_BODY = 1024

# Global variable to hold the server instance
global_server = None

_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL",
                     *(f"COM{i}" for i in range(1, 10)),
                     *(f"LPT{i}" for i in range(1, 10))}

def sanitize_filename(name: str) -> str:
    name = name.replace('\\', '/').rsplit('/', 1)[-1]
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    name = name.strip().strip('.')
    if not name:
        return "unnamed"
    # Windows treats "aux.tar.gz" like "aux", so check everything before the first dot
    stem = name.split('.', 1)[0]
    if stem.upper() in _WINDOWS_RESERVED:
        name = '_' + name
    return name

def resolve_unique_path(target_dir: Path, filename: str) -> Path:
    candidate = target_dir / filename
    if not candidate.exists():
        return candidate
    if '.' in filename:
        stem, ext = filename.rsplit('.', 1)
        ext = '.' + ext
    else:
        stem, ext = filename, ''
    i = 1
    while True:
        candidate = target_dir / f"{stem} ({i}){ext}"
        if not candidate.exists():
            return candidate
        i += 1

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

@app.get("/api/files", dependencies=[Depends(require_session)])
async def list_files(path: str = ""):
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
async def get_thumb(path: str):
    real_path = resolve_in_root(path)
    import hashlib
    hash_name = hashlib.md5(str(real_path).encode('utf-8')).hexdigest() + ".jpg"
    thumb_path = config.THUMB_CACHE_DIR / hash_name
    
    if thumb_path.exists(): return FileResponse(thumb_path)
    if real_path.is_file():
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(executor, generate_thumbnail, real_path, thumb_path)
        if success: return FileResponse(thumb_path)
    raise HTTPException(404)

@app.get("/api/download", dependencies=[Depends(require_session)])
async def download_file(path: str):
    real_path = resolve_in_root(path)
    if real_path.is_file(): return FileResponse(real_path, filename=real_path.name)
    raise HTTPException(404)

@app.get("/api/download_folder", dependencies=[Depends(require_session)])
async def download_folder(path: str):
    real_path = resolve_in_root(path)
    if not real_path.is_dir(): raise HTTPException(400)
    temp_zip = config.THUMB_CACHE_DIR / f"dl_{uuid.uuid4().hex}.zip"
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(executor, shutil.make_archive, str(temp_zip).replace('.zip',''), 'zip', real_path)
    except Exception:
        temp_zip.unlink(missing_ok=True)
        raise
    return FileResponse(temp_zip, filename=f"{real_path.name}.zip", background=BackgroundTask(temp_zip.unlink))

@app.get("/api/view", dependencies=[Depends(require_session)])
async def view_media(path: str):
    real_path = resolve_in_root(path)
    if real_path.is_file(): return FileResponse(real_path)
    raise HTTPException(404)

@app.get("/api/server_info", dependencies=[Depends(require_session)])
async def server_info():
    return {"allow_upload": bool(config.ALLOW_UPLOAD), "require_code": access.require_code}

@app.post("/api/upload", dependencies=[Depends(require_session)])
async def upload_file(file: UploadFile = File(...)):
    if not config.ALLOW_UPLOAD:
        raise HTTPException(403, "Uploads are disabled")
    if not config.UPLOAD_DIR:
        raise HTTPException(500, "Upload directory is not configured")

    upload_dir = Path(config.UPLOAD_DIR).resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_name = sanitize_filename(file.filename or "")
    target_path = resolve_unique_path(upload_dir, safe_name)

    try:
        target_path.resolve().relative_to(upload_dir)
    except ValueError:
        raise HTTPException(400, "Invalid upload path")

    total_written = 0
    try:
        async with aiofiles.open(target_path, 'wb') as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                await out.write(chunk)
                total_written += len(chunk)
    except Exception as e:
        try:
            if target_path.exists():
                target_path.unlink()
        except Exception:
            pass
        raise HTTPException(500, f"Upload failed: {e}")
    finally:
        await file.close()

    try:
        rel_path = str(target_path.resolve().relative_to(Path(config.ROOT_DIR).resolve())).replace("\\", "/")
        saved_outside_root = False
    except ValueError:
        rel_path = None
        saved_outside_root = True

    return JSONResponse({
        "name": target_path.name,
        "size": total_written,
        "path": rel_path,
        "saved_outside_root": saved_outside_root,
    })

# Before the static mount. It only matches code-shaped segments, so static files (which have dots) still reach the mount
@app.get("/{code:access_code}", include_in_schema=False)
async def enter_with_code(code: str, request: Request):
    if not access.require_code: return RedirectResponse("/", 303)
    return start_session(request, code, RedirectResponse("/", 303))

if os.path.exists(config.FRONTEND_DIST_DIR):
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIST_DIR, html=True), name="static")

def run_server():
    global global_server
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["handlers"]["default"]["stream"] = "ext://sys.stderr"
    log_config["handlers"]["access"]["stream"] = "ext://sys.stdout"
    
    config_uvicorn = uvicorn.Config(app, host="0.0.0.0", port=config.PORT, log_level="error", log_config=log_config)
    global_server = uvicorn.Server(config_uvicorn)
    global_server.run()

def stop_server_logic():
    global global_server
    if global_server:
        global_server.should_exit = True