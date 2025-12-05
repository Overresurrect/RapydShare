import os
import uvicorn
import secrets
import mimetypes
import shutil
import asyncio
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles 

from src.config import config
from src.utils import generate_thumbnail

executor = ThreadPoolExecutor(max_workers=4)
security = HTTPBasic(auto_error=False)
app = FastAPI()

# Global variable to hold the server instance
global_server = None

def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    if not config.USE_AUTH: return "guest"
    if not credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Auth required", {"WWW-Authenticate": "Basic"})
    
    is_correct = (secrets.compare_digest(credentials.username, config.USERNAME) and 
                  secrets.compare_digest(credentials.password, config.PASSWORD))
    
    if not is_correct:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid creds", {"WWW-Authenticate": "Basic"})
    return credentials.username

@app.get("/api/files", dependencies=[Depends(get_current_username)])
async def list_files(path: str = ""):
    req_path = (Path(config.ROOT_DIR) / path).resolve()
    if not str(req_path).startswith(str(Path(config.ROOT_DIR).resolve())): raise HTTPException(403)
    if not req_path.exists(): raise HTTPException(404)
    
    items = []
    try:
        with os.scandir(req_path) as entries:
            for entry in entries:
                try:
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
    return items

@app.get("/api/thumb", dependencies=[Depends(get_current_username)])
async def get_thumb(path: str):
    real_path = (Path(config.ROOT_DIR) / path).resolve()
    import hashlib
    hash_name = hashlib.md5(str(real_path).encode('utf-8')).hexdigest() + ".jpg"
    thumb_path = config.THUMB_CACHE_DIR / hash_name
    
    if thumb_path.exists(): return FileResponse(thumb_path)
    if real_path.exists():
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(executor, generate_thumbnail, real_path, thumb_path)
        if success: return FileResponse(thumb_path)
    raise HTTPException(404)

@app.get("/api/download", dependencies=[Depends(get_current_username)])
async def download_file(path: str):
    real_path = (Path(config.ROOT_DIR) / path).resolve()
    if real_path.is_file(): return FileResponse(real_path, filename=real_path.name)
    raise HTTPException(404)

@app.get("/api/download_folder", dependencies=[Depends(get_current_username)])
async def download_folder(path: str):
    real_path = (Path(config.ROOT_DIR) / path).resolve()
    if not real_path.is_dir(): raise HTTPException(400)
    temp_zip = config.THUMB_CACHE_DIR / f"dl_{int(datetime.now().timestamp())}.zip"
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(executor, shutil.make_archive, str(temp_zip).replace('.zip',''), 'zip', real_path)
    return FileResponse(temp_zip, filename=f"{real_path.name}.zip")

@app.get("/api/view", dependencies=[Depends(get_current_username)])
async def view_media(path: str):
    real_path = (Path(config.ROOT_DIR) / path).resolve()
    if real_path.exists(): return FileResponse(real_path)
    raise HTTPException(404)

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