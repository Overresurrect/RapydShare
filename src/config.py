import sys
import os
import tempfile
from pathlib import Path

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class ServerConfig:
    ROOT_DIR = ""
    PORT = 8000
    USE_AUTH = False
    USERNAME = "admin"
    PASSWORD = "password"
    # Temp folder for thumbs
    THUMB_CACHE_DIR = Path(tempfile.gettempdir()) / "RapydShare_Thumbs"

    # Locations
    FRONTEND_DIST_DIR = get_resource_path(os.path.join("frontend", "dist"))
    ICON_PATH = get_resource_path(os.path.join("assets", "RapydShare.ico"))

config = ServerConfig()

# Ensure thumb dir exists
if config.THUMB_CACHE_DIR.exists():
    try:
        import shutil
        shutil.rmtree(config.THUMB_CACHE_DIR)
    except: pass
config.THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)