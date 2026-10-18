import sys
import os

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
    REQUIRE_CODE = True
    ALLOW_UPLOAD = False
    UPLOAD_DIR = ""
    # Per-run folder for thumbs, set while the server runs
    THUMB_CACHE_DIR = None

    # Locations
    FRONTEND_DIST_DIR = get_resource_path(os.path.join("frontend", "dist"))
    ICON_PATH = get_resource_path(os.path.join("assets", "RapydShare.ico"))

config = ServerConfig()
