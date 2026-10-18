import os
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image, ImageFile, JpegImagePlugin

from src import server, thumbs
from src.config import config

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def cache(tmp_path):
    folder = tmp_path / "thumbs"
    folder.mkdir()
    return folder


@pytest.fixture
def decodes(monkeypatch):
    """Lists every time Pillow decodes image data."""
    calls = []
    real_load = ImageFile.ImageFile.load

    def load(self, *args):
        calls.append(self)
        return real_load(self, *args)

    monkeypatch.setattr(ImageFile.ImageFile, "load", load)
    return calls


def save_image(path, size=(8, 8), color="red"):
    Image.new("RGB", size, color).save(path)
    return path


def jpeg_color(path):
    with Image.open(path) as img:
        return img.convert("RGB").getpixel((0, 0))


def test_makes_a_jpeg_thumbnail_no_bigger_than_the_cap(tmp_path, cache):
    thumb = thumbs.thumb_for(save_image(tmp_path / "big.png", (900, 600)), cache)
    with Image.open(thumb) as img:
        assert img.format == "JPEG"
        assert max(img.size) == 300


def test_refuses_an_image_over_the_pixel_cap_before_decoding(tmp_path, cache, decodes):
    src = tmp_path / "huge.png"
    Image.new("1", (8000, 7000)).save(src)  # 56 million pixels, a few KB on disk
    assert thumbs.thumb_for(src, cache) is None
    assert decodes == []


def test_decodes_an_image_under_the_cap(tmp_path, cache, decodes):
    assert thumbs.thumb_for(save_image(tmp_path / "ok.png"), cache) is not None
    assert decodes


def test_asks_jpeg_for_a_smaller_decode(tmp_path, cache, monkeypatch):
    sizes = []
    real_draft = JpegImagePlugin.JpegImageFile.draft

    def draft(self, mode, size):
        sizes.append(size)
        return real_draft(self, mode, size)

    monkeypatch.setattr(JpegImagePlugin.JpegImageFile, "draft", draft)
    thumbs.thumb_for(save_image(tmp_path / "a.jpg", (900, 600)), cache)
    assert sizes


@pytest.mark.parametrize("name", ["a.tiff", "a.ico", "a.svg", "a.txt", "a.psd", "noext"])
def test_no_thumbnail_for_formats_outside_the_allowlist(tmp_path, cache, name):
    src = tmp_path / name
    Image.new("RGB", (8, 8)).save(src, format="TIFF")
    assert thumbs.thumb_for(src, cache) is None


def test_no_thumbnail_when_the_content_is_not_an_allowed_format(tmp_path, cache):
    src = tmp_path / "pretending.png"
    Image.new("RGB", (8, 8)).save(src, format="TIFF")
    assert thumbs.thumb_for(src, cache) is None


@pytest.mark.parametrize("name", ["a.jpg", "a.png", "a.gif", "a.webp", "a.bmp"])
def test_thumbnails_every_allowed_image_format(tmp_path, cache, name):
    assert thumbs.thumb_for(save_image(tmp_path / name), cache) is not None


def test_image_size_cap(tmp_path, cache, monkeypatch):
    src = save_image(tmp_path / "a.png")
    monkeypatch.setattr(thumbs, "MAX_IMAGE_BYTES", src.stat().st_size - 1)
    assert thumbs.thumb_for(src, cache) is None
    monkeypatch.setattr(thumbs, "MAX_IMAGE_BYTES", src.stat().st_size)
    assert thumbs.thumb_for(src, cache) is not None


def test_video_size_cap(tmp_path, cache, monkeypatch):
    opened = []
    real_capture = cv2.VideoCapture
    monkeypatch.setattr(thumbs.cv2, "VideoCapture", lambda path: opened.append(path) or real_capture(path))
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"not really a video")
    monkeypatch.setattr(thumbs, "MAX_VIDEO_BYTES", src.stat().st_size - 1)
    assert thumbs.thumb_for(src, cache) is None
    assert opened == []
    monkeypatch.setattr(thumbs, "MAX_VIDEO_BYTES", src.stat().st_size)
    assert thumbs.thumb_for(src, cache) is None
    assert opened


def make_video(path):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48))
    if not writer.isOpened():
        pytest.skip("No video encoder here")
    for _ in range(40):
        writer.write(np.full((48, 64, 3), (0, 0, 255), np.uint8))
    writer.release()
    return path


def test_thumbnails_a_video(tmp_path, cache):
    thumb = thumbs.thumb_for(make_video(tmp_path / "clip.avi"), cache)
    if thumb is None:
        pytest.skip("No video decoder here")
    with Image.open(thumb) as img:
        assert img.format == "JPEG"


def test_a_changed_file_gets_a_new_thumbnail(tmp_path, cache):
    src = save_image(tmp_path / "a.png", color="red")
    first = thumbs.thumb_for(src, cache)
    save_image(src, color="blue")
    os.utime(src, ns=(0, src.stat().st_mtime_ns + 1_000_000_000))
    second = thumbs.thumb_for(src, cache)
    assert first != second
    assert jpeg_color(first)[0] > 200
    assert jpeg_color(second)[2] > 200


def test_a_touched_file_gets_a_new_cache_name(tmp_path):
    src = save_image(tmp_path / "a.png")
    before = thumbs.cache_name(src.stat())
    os.utime(src, ns=(0, src.stat().st_mtime_ns + 1_000_000_000))
    assert thumbs.cache_name(src.stat()) != before


def test_the_same_file_reuses_its_thumbnail(tmp_path, cache, monkeypatch):
    src = save_image(tmp_path / "a.png")
    first = thumbs.thumb_for(src, cache)
    monkeypatch.setattr(thumbs, "make_thumb", lambda *args: pytest.fail("made it again"))
    assert thumbs.thumb_for(src, cache) == first


def test_a_missing_file_has_no_thumbnail_even_when_cached(tmp_path, cache):
    src = save_image(tmp_path / "a.png")
    assert thumbs.thumb_for(src, cache) is not None
    src.unlink()
    assert thumbs.thumb_for(src, cache) is None


def test_a_folder_has_no_thumbnail(tmp_path, cache):
    folder = tmp_path / "pics.png"
    folder.mkdir()
    assert thumbs.thumb_for(folder, cache) is None


def test_a_failure_is_recorded_and_not_retried(tmp_path, cache, monkeypatch):
    src = tmp_path / "broken.png"
    src.write_bytes(b"not a png")
    attempts = []
    real_make = thumbs.make_thumb
    monkeypatch.setattr(thumbs, "make_thumb", lambda *args: attempts.append(args) or real_make(*args))
    assert thumbs.thumb_for(src, cache) is None
    assert thumbs.thumb_for(src, cache) is None
    assert len(attempts) == 1


def test_a_replaced_broken_file_is_tried_again(tmp_path, cache):
    src = tmp_path / "a.png"
    src.write_bytes(b"not a png")
    assert thumbs.thumb_for(src, cache) is None
    save_image(src)
    os.utime(src, ns=(0, src.stat().st_mtime_ns + 1_000_000_000))
    assert thumbs.thumb_for(src, cache) is not None


def test_a_failure_is_recorded_without_leaving_a_thumbnail(tmp_path, cache):
    src = tmp_path / "broken.png"
    src.write_bytes(b"not a png")
    thumbs.thumb_for(src, cache)
    assert not [p for p in cache.iterdir() if p.suffix == ".jpg"]


def test_only_the_finished_thumbnail_is_left_in_the_cache(tmp_path, cache):
    thumb = thumbs.thumb_for(save_image(tmp_path / "a.png"), cache)
    assert list(cache.iterdir()) == [thumb]


def test_a_failed_write_leaves_no_partial_file(tmp_path, cache, monkeypatch):
    src = save_image(tmp_path / "a.png")

    def broken_save(self, fp, *args, **kwargs):
        Path(fp).write_bytes(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(Image.Image, "save", broken_save)
    assert thumbs.thumb_for(src, cache) is None
    assert [p.name for p in cache.iterdir() if not p.name.endswith(".failed")] == []


def test_endpoint_serves_a_thumbnail(client):
    r = client.get("/api/thumb", params={"path": "photo.png"})
    assert r.status_code == 200
    assert r.content[:3] == b"\xff\xd8\xff"


def test_endpoint_returns_404_for_a_deleted_file_even_when_cached(client, share):
    assert client.get("/api/thumb", params={"path": "photo.png"}).status_code == 200
    (share / "photo.png").unlink()
    assert client.get("/api/thumb", params={"path": "photo.png"}).status_code == 404


def test_endpoint_serves_the_new_picture_after_the_file_changes(client, share):
    first = client.get("/api/thumb", params={"path": "photo.png"}).content
    save_image(share / "photo.png", color="blue")
    os.utime(share / "photo.png", ns=(0, (share / "photo.png").stat().st_mtime_ns + 1_000_000_000))
    second = client.get("/api/thumb", params={"path": "photo.png"}).content
    assert first != second


def test_endpoint_returns_404_for_an_unsupported_file(client):
    assert client.get("/api/thumb", params={"path": "hello.txt"}).status_code == 404


def test_endpoint_returns_404_when_no_cache_folder_is_open(client, monkeypatch):
    monkeypatch.setattr(config, "THUMB_CACHE_DIR", None)
    assert client.get("/api/thumb", params={"path": "photo.png"}).status_code == 404


def test_open_and_close_cache_dir(monkeypatch):
    monkeypatch.setattr(config, "THUMB_CACHE_DIR", None)
    folder = server.open_cache_dir()
    try:
        assert folder.is_dir()
        assert folder.name.startswith("RapydShare_")
        assert config.THUMB_CACHE_DIR == folder
        (folder / "x.jpg").write_bytes(b"x")
    finally:
        server.close_cache_dir()
    assert not folder.exists()
    assert config.THUMB_CACHE_DIR is None


def test_each_run_gets_its_own_cache_dir(monkeypatch):
    monkeypatch.setattr(config, "THUMB_CACHE_DIR", None)
    first = server.open_cache_dir()
    server.close_cache_dir()
    second = server.open_cache_dir()
    server.close_cache_dir()
    assert first != second


def test_close_cache_dir_without_one_open_is_fine(monkeypatch):
    monkeypatch.setattr(config, "THUMB_CACHE_DIR", None)
    server.close_cache_dir()
    assert config.THUMB_CACHE_DIR is None


def test_config_starts_without_a_cache_dir():
    from src.config import ServerConfig
    assert ServerConfig.THUMB_CACHE_DIR is None


def test_thumbs_does_not_load_qt():
    code = "import sys, src.thumbs; sys.exit('PyQt6' in sys.modules or 'src.utils' in sys.modules)"
    assert subprocess.run([sys.executable, "-c", code], cwd=ROOT).returncode == 0
