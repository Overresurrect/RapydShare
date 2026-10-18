import hashlib
import mimetypes
import os
import stat
import uuid
from pathlib import Path

import cv2
from PIL import Image

MAX_IMAGE_BYTES = 200 * 1024 ** 2
MAX_VIDEO_BYTES = 4 * 1024 ** 3
MAX_PIXELS = 50_000_000
THUMB_SIZE = (300, 300)
IMAGE_FORMATS = {"JPEG", "PNG", "GIF", "WEBP", "BMP"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


def cache_name(st: os.stat_result) -> str:
    """Names a thumbnail after the file's identity and version, so a changed file gets a new one."""
    key = f"{st.st_dev}:{st.st_ino}:{st.st_mtime_ns}:{st.st_size}"
    return hashlib.sha256(key.encode()).hexdigest()


def source_kind(path: Path, size: int) -> str | None:
    """"image" or "video" if the file is of a kind, and small enough, to thumbnail."""
    if path.suffix.lower() in IMAGE_EXTENSIONS:
        return "image" if size <= MAX_IMAGE_BYTES else None
    mime, _ = mimetypes.guess_type(path.name)
    return "video" if mime and mime.startswith("video/") and size <= MAX_VIDEO_BYTES else None


def image_thumb(path: Path):
    """The thumbnail image, or None for a format outside the allowlist or an image over the pixel cap (both checked before any decoding)."""
    with Image.open(path) as img:
        if img.format not in IMAGE_FORMATS or img.width * img.height > MAX_PIXELS: return None
        if img.format == "JPEG": img.draft("RGB", THUMB_SIZE)
        if img.mode not in ("RGB", "L"): img = img.convert("RGB")
        img.thumbnail(THUMB_SIZE)
        return img.copy()


def video_thumb(path: Path):
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened(): return None
        # Jump to 33%
        total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if total > 30: cap.set(cv2.CAP_PROP_POS_FRAMES, int(total / 3))
        ok, frame = cap.read()
    finally:
        cap.release()
    if not ok: return None
    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    img.thumbnail(THUMB_SIZE)
    return img


def make_thumb(path: Path, kind: str, thumb: Path) -> bool:
    """Writes the thumbnail to thumb in one step, so a half-written file is never served."""
    partial = thumb.with_name(f"{thumb.name}.{uuid.uuid4().hex}.tmp")
    try:
        img = image_thumb(path) if kind == "image" else video_thumb(path)
        if img is None: return False
        img.save(partial, "JPEG", quality=60)
        os.replace(partial, thumb)
        return True
    except Exception:
        return False
    finally:
        partial.unlink(missing_ok=True)


def thumb_for(path: Path, cache_dir: Path) -> Path | None:
    """The cached thumbnail of path, made if needed. None if the file is gone or can't be thumbnailed. Failures are remembered, not retried."""
    try:
        st = path.stat()
    except OSError:
        return None
    kind = source_kind(path, st.st_size) if stat.S_ISREG(st.st_mode) else None
    if kind is None: return None
    name = cache_name(st)
    thumb = cache_dir / f"{name}.jpg"
    failed = cache_dir / f"{name}.failed"
    if thumb.exists(): return thumb
    if failed.exists(): return None
    if make_thumb(path, kind, thumb): return thumb
    try:
        failed.touch()
    except OSError:
        pass
    return None
