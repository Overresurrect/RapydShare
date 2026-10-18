import pytest

from src.config import config


@pytest.fixture
def uploads(share, monkeypatch):
    """Turns uploads on, into shared/uploads, and returns that folder."""
    folder = share / "uploads"
    folder.mkdir()
    monkeypatch.setattr(config, "ALLOW_UPLOAD", True)
    monkeypatch.setattr(config, "UPLOAD_DIR", str(folder))
    return folder


def upload(client, filename, content=b"data"):
    return client.post("/api/upload", files={"file": (filename, content)})


def test_refused_when_uploads_are_off(client, share):
    r = upload(client, "report.txt")
    assert r.status_code == 403
    assert not (share / "report.txt").exists()


def test_saves_the_file(client, uploads):
    r = upload(client, "report.txt", b"quarterly numbers")
    assert r.status_code == 200
    assert (uploads / "report.txt").read_bytes() == b"quarterly numbers"
    assert r.json() == {
        "name": "report.txt",
        "size": 17,
        "path": "uploads/report.txt",
        "saved_outside_root": False,
    }


def test_never_overwrites_an_existing_file(client, uploads):
    names = [upload(client, "report.txt", body).json()["name"] for body in (b"one", b"two", b"three")]
    assert names == ["report.txt", "report (1).txt", "report (2).txt"]
    assert (uploads / "report.txt").read_bytes() == b"one"
    assert (uploads / "report (2).txt").read_bytes() == b"three"


def test_numbers_files_without_an_extension(client, uploads):
    upload(client, "README")
    assert upload(client, "README").json()["name"] == "README (1)"


@pytest.mark.parametrize("filename", [
    "../../escaped.txt",
    "..\\..\\escaped.txt",
    "/tmp/escaped.txt",
])
def test_paths_in_the_filename_are_dropped(client, uploads, filename):
    r = upload(client, filename)
    assert r.status_code == 200
    assert r.json()["name"] == "escaped.txt"
    assert (uploads / "escaped.txt").exists()
    assert not (uploads.parent.parent / "escaped.txt").exists()


def test_reports_uploads_outside_the_shared_folder(client, share, monkeypatch, tmp_path):
    outside = tmp_path / "inbox"
    outside.mkdir()
    monkeypatch.setattr(config, "ALLOW_UPLOAD", True)
    monkeypatch.setattr(config, "UPLOAD_DIR", str(outside))

    r = upload(client, "report.txt")
    assert r.status_code == 200
    assert (outside / "report.txt").exists()
    assert r.json()["path"] is None
    assert r.json()["saved_outside_root"] is True
