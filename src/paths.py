import sys
from pathlib import Path, PureWindowsPath

from fastapi import HTTPException

from src.config import config


def path_text_is_safe(path: str) -> bool:
    # Parsed as a Windows path on every platform, so macOS CI catches the Windows forms too
    if "\x00" in path or ":" in path:
        return False
    if path.startswith(("/", "\\")):
        return False
    parsed = PureWindowsPath(path)
    return not (parsed.drive or parsed.root)


def _is_alias(path: str) -> bool:
    """Names the OS treats as another file: "a.txt." on Windows, "a.txt/..namedfork/rsrc" on macOS."""
    parts = PureWindowsPath(path).parts
    if sys.platform == "win32":
        return any(p not in (".", "..") and p.endswith((".", " ")) for p in parts)
    if sys.platform == "darwin":
        return any(p.lower() == "..namedfork" for p in parts)
    return False


def resolve_in_root(path: str) -> Path:
    if not config.ROOT_DIR:
        raise HTTPException(503)
    if not path_text_is_safe(path):
        raise HTTPException(403)
    if _is_alias(path):
        raise HTTPException(404)
    try:
        root = Path(config.ROOT_DIR).resolve()
        real_path = (root / path).resolve()
        if not real_path.is_relative_to(root):
            raise HTTPException(403)
        real_path.stat()
    except (OSError, ValueError, RuntimeError):
        raise HTTPException(404)
    return real_path
