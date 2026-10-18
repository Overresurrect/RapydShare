import os
import sys
import socket
import cv2
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
