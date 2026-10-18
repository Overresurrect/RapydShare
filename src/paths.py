import os
import stat
import sys
from pathlib import Path, PureWindowsPath

from fastapi import HTTPException

from src.config import config

HIDDEN_NAMES = {"desktop.ini", "thumbs.db", "$recycle.bin", "system volume information"}


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


def is_hidden_name(name: str) -> bool:
    return name.startswith(".") or name.lower() in HIDDEN_NAMES


def is_hidden(path: Path) -> bool:
    """True for hidden names and for entries with the OS hidden flag. The flag is read off the entry itself, not a link's target."""
    if is_hidden_name(path.name):
        return True
    if path == Path(path.anchor):
        return False  # NTFS drive roots carry the Hidden and System attributes
    try:
        st = path.lstat()
    except OSError:
        return True
    if sys.platform == "darwin":
        return bool(st.st_flags & stat.UF_HIDDEN)
    if sys.platform == "win32":
        return bool(st.st_file_attributes & (stat.FILE_ATTRIBUTE_HIDDEN | stat.FILE_ATTRIBUTE_SYSTEM))
    return False


def resolves_inside(path: Path, root: Path) -> bool:
    """root must already be resolved."""
    try:
        return path.resolve().is_relative_to(root)
    except (OSError, ValueError, RuntimeError):
        return False


def _names_hidden(path: str) -> bool:
    return any(p not in (".", "..") and is_hidden_name(p) for p in PureWindowsPath(path).parts)


def hidden_below(path: Path, root: Path) -> bool:
    """True if any component of path below root is hidden. path must be resolved and inside root."""
    parts = path.relative_to(root).parts
    return any(is_hidden(root.joinpath(*parts[:i + 1])) for i in range(len(parts)))


def is_link(path: Path) -> bool:
    """Symlinks, and Windows junctions, which resolve() follows but is_symlink() doesn't report."""
    return path.is_symlink() or os.path.isjunction(path)


def _name_is_servable(name: str) -> bool:
    # On macOS "a:b" is refused by resolve_in_root, and "\" reads as a folder there and in the listing's paths
    return ":" not in name and "\\" not in name and not _is_alias(name)


def is_listable(entry: Path, root: Path) -> bool:
    """The listing's version of resolve_in_root's checks: the entry is not hidden, and neither is anything it resolves to.

    entry's folder must be resolved, inside root and already checked, so only links need resolving.
    """
    if not _name_is_servable(entry.name) or is_hidden(entry):
        return False
    if not is_link(entry):
        return True
    return resolves_inside(entry, root) and not hidden_below(entry.resolve(), root)


def resolve_in_root(path: str) -> Path:
    if not config.ROOT_DIR:
        raise HTTPException(503)
    if not path_text_is_safe(path):
        raise HTTPException(403)
    if _is_alias(path) or _names_hidden(path):
        raise HTTPException(404)
    try:
        root = Path(config.ROOT_DIR).resolve()
        real_path = (root / path).resolve()
        if not real_path.is_relative_to(root):
            raise HTTPException(403)
        real_path.stat()
        if hidden_below(real_path, root):
            raise HTTPException(404)
    except (OSError, ValueError, RuntimeError):
        raise HTTPException(404)
    return real_path


def _os_folders() -> list[Path]:
    if sys.platform == "win32":
        names = ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "ProgramData")
        return [Path(os.environ[n]) for n in names if n in os.environ]
    return [Path(p) for p in ("/System", "/Library", "/Applications", "/usr", "/bin", "/sbin", "/etc", "/private", "/var")]


def _system_root() -> Path:
    return Path(os.environ.get("SystemDrive", "C:") + "\\") if sys.platform == "win32" else Path("/")


def _is_or_inside(path: Path, folder: Path) -> bool:
    return path == folder or path.is_relative_to(folder)


def refuse_share_folder(folder: str) -> str | None:
    """Why folder can't be shared, in words for the user, or None if it can. Never raises."""
    if not folder.strip():
        return "Choose a folder to share."
    try:
        return _refuse_share_folder(folder)
    except (OSError, ValueError, RuntimeError):
        return "That folder can't be opened."


def _refuse_share_folder(folder: str) -> str | None:
    path = Path(folder.strip()).resolve()
    if not path.is_dir():
        return "That folder doesn't exist."
    home = Path.home().resolve()
    if path == home:
        return "That's your whole home folder. Choose a folder inside it."
    if path == _system_root().resolve():
        return "That's the whole system drive. Choose a smaller folder."
    if home.is_relative_to(path):
        return "That folder contains your home folder. Choose a folder inside it."
    inside_home = path.is_relative_to(home)
    if not inside_home and any(_is_or_inside(path, f.resolve()) for f in _os_folders()):
        return "That's a system folder. Choose a different one."
    # ~/Library is hidden, but the cloud folders inside it are meant to be used
    base = next((c for c in _cloud_roots(home) if path.is_relative_to(c)), home)
    if is_hidden(path) or (inside_home and hidden_below(path, base)):
        return "That folder is hidden. Choose a different one."
    return None


def _cloud_roots(home: Path) -> list[Path]:
    """Where iCloud Drive, and Dropbox, OneDrive, Google Drive and Box, keep their folders on macOS."""
    return [home / "Library" / "Mobile Documents", home / "Library" / "CloudStorage"]
