import os
import sys
import mimetypes
import socket
import cv2
from PIL import Image
from pathlib import Path
# --- Added these new imports ---
import qrcode
import io
from PyQt6.QtGui import QPixmap

# Fix console logging for EXE
def setup_logging_hack():
    if sys.stdout is None: sys.stdout = open(os.devnull, "w")
    if sys.stderr is None: sys.stderr = open(os.devnull, "w")
    # Silence OpenCV
    os.environ["OPENCV_LOG_LEVEL"] = "OFF"
    os.environ["OPENCV_FFMPEG_LOG_LEVEL"] = "quiet"
    try:
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
    except: pass

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def generate_qr_code_pixmap(url: str, size: int = 220) -> QPixmap:
    """
    Generates a QR code for the given URL and returns it as a QPixmap.
    Avoids saving any temporary files to disk.
    """
    # Generate the QR code image object
    qr_img = qrcode.make(url)

    # Save the image to an in-memory bytes buffer
    buffer = io.BytesIO()
    qr_img.save(buffer, "PNG")

    # Create a QPixmap and load the image data from the buffer
    pixmap = QPixmap()
    pixmap.loadFromData(buffer.getvalue(), "PNG")

    # Scale the pixmap to the desired size
    return pixmap.scaled(size, size)

def generate_thumbnail(file_path: Path, thumb_path: Path):
    try:
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type: return False

        if mime_type.startswith('image'):
            with Image.open(file_path) as img:
                if img.mode in ("RGBA", "P"): img = img.convert("RGB")
                img.thumbnail((300, 300))
                img.save(thumb_path, "JPEG", quality=60)
                return True

        elif mime_type.startswith('video'):
            cap = cv2.VideoCapture(str(file_path))
            if not cap.isOpened(): return False
            # Jump to 33%
            total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            if total > 30: cap.set(cv2.CAP_PROP_POS_FRAMES, int(total / 3))
            
            ret, frame = cap.read()
            cap.release()
            if ret:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame)
                img.thumbnail((300, 300))
                img.save(thumb_path, "JPEG", quality=60)
                return True
    except: return False
    return False