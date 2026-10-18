import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6")
pytest.importorskip("qfluentwidgets")

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QFileDialog

from src import gui, server
from src.access import access
from src.config import config


@pytest.fixture(scope="module")
def qapp():
    try:
        return QApplication.instance() or QApplication([])
    except Exception as e:
        pytest.skip(f"Qt can't start here: {e}")


@pytest.fixture
def settings(tmp_path):
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


@pytest.fixture
def home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "Photos").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


@pytest.fixture
def bars(monkeypatch):
    """Records every message the window shows as (kind, title, content)."""
    shown = []
    for kind in ("success", "info", "warning", "error"):
        monkeypatch.setattr(gui.InfoBar, kind,
                            lambda *a, _kind=kind, **k: shown.append((_kind, k["title"], k["content"])))
    return shown


@pytest.fixture
def window(qapp, settings, home, bars):
    w = gui.ServerLauncher(settings)
    yield w
    w.close()
    w.deleteLater()
    server.stop_server()


@pytest.fixture
def local_only(monkeypatch):
    """Start binds 127.0.0.1 on any free port, and the address never asks the network for an IP."""
    real = server.open_listen_socket
    monkeypatch.setattr(server, "open_listen_socket", lambda port: real(0, host="127.0.0.1"))
    monkeypatch.setattr(gui, "get_local_ip", lambda: "127.0.0.1")
    for name in ("ROOT_DIR", "PORT", "ALLOW_UPLOAD", "UPLOAD_DIR", "REQUIRE_CODE"):
        monkeypatch.setattr(config, name, getattr(config, name))


def wait_for(qapp, condition, seconds=5):
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        qapp.processEvents()
        time.sleep(0.01)


def start(qapp, window, folder):
    window.folder_input.setText(str(folder))
    window.start_server()
    wait_for(qapp, lambda: window.btn_copy.isEnabled())


# --- Defaults ---

def test_the_folder_box_starts_empty_with_a_placeholder(window):
    assert window.folder_input.text() == ""
    assert window.folder_input.placeholderText() == "Choose a folder to share…"


def test_the_window_is_a_fixed_size(window):
    assert (window.width(), window.height()) == (680, 740)


def test_the_access_code_switch_is_on_by_default(window):
    assert window.switch_code.isChecked()


def test_there_are_no_username_or_password_fields(window):
    for name in ("user_input", "pass_input", "switch_auth"):
        assert not hasattr(window, name)


def test_the_not_encrypted_note_is_visible(window):
    window.show()
    assert window.note_label.text() == "Not encrypted. Use on networks you trust."
    assert window.note_label.isVisible()


def test_everything_fits_in_the_window(window):
    window.show()
    for widget in (window.folder_input, window.port_input, window.switch_code, window.note_label,
                   window.upload_folder_input, window.btn_toggle, window.status_label,
                   window.code_label, window.btn_copy, window.url_label):
        corner = widget.mapTo(window, widget.rect().bottomRight())
        assert 0 <= corner.y() < window.height() and 0 <= corner.x() < window.width()


def test_turning_the_code_off_shows_a_warning(window, bars):
    window.switch_code.setChecked(False)
    assert len(bars) == 1
    kind, title, content = bars[0]
    assert kind == "warning" and "anyone" in content.lower()


def test_turning_the_code_back_on_shows_nothing(window, bars):
    window.switch_code.setChecked(False)
    bars.clear()
    window.switch_code.setChecked(True)
    assert bars == []


# --- The folder ---

def test_a_remembered_folder_fills_the_box(qapp, settings, home, bars):
    settings.setValue("folder", str(home / "Photos"))
    assert gui.ServerLauncher(settings).folder_input.text() == str(home / "Photos")


def test_a_remembered_folder_that_is_gone_is_ignored(qapp, settings, home, bars):
    settings.setValue("folder", str(home / "gone"))
    assert gui.ServerLauncher(settings).folder_input.text() == ""


def test_picking_a_folder_remembers_it(window, settings, home, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(home / "Photos"))
    window.browse_folder()
    assert window.folder_input.text() == str(home / "Photos")
    assert settings.value("folder") == str(home / "Photos")


def test_picking_a_refused_folder_says_so_and_is_not_remembered(window, settings, home, bars, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(home))
    window.browse_folder()
    assert settings.value("folder") is None
    assert [kind for kind, *_ in bars] == ["error"]


def test_starting_remembers_the_folder(qapp, window, settings, home, local_only):
    start(qapp, window, home / "Photos")
    assert settings.value("folder") == str(home / "Photos")


def test_start_refuses_without_a_folder(window, bars, local_only):
    window.start_server()
    assert not window.is_running
    assert window.server_thread is None
    assert not server.server_started()
    assert [kind for kind, *_ in bars] == ["error"]


def test_start_refuses_the_home_folder(window, home, bars, local_only):
    window.folder_input.setText(str(home))
    window.start_server()
    assert not window.is_running and not server.server_started()
    assert [kind for kind, *_ in bars] == ["error"]


# --- Running ---

def test_start_shows_the_code_and_a_copy_link_button_and_stop_clears_them(qapp, window, home, local_only):
    start(qapp, window, home / "Photos")

    code = access.code
    assert code is not None and len(code) == 6
    assert window.code_label.text() == f"{code[:3]} {code[3:]}"
    assert window.btn_copy.text() == "Copy link"
    assert window.link == f"http://127.0.0.1:{config.PORT}/{code}"
    assert window.is_running

    window.stop_server()

    assert not window.is_running
    assert window.code_label.text() == ""
    assert not window.btn_copy.isEnabled()
    assert window.btn_toggle.isEnabled()
    assert window.status_label.text() == "Ready"
    assert not server.server_started()


def test_start_with_the_code_off_shows_no_code(qapp, window, home, local_only):
    window.switch_code.setChecked(False)
    start(qapp, window, home / "Photos")
    assert access.code is None
    assert window.code_label.text() == ""
    assert window.link == f"http://127.0.0.1:{config.PORT}"


def test_copy_link_copies_the_address(qapp, window, home, local_only):
    start(qapp, window, home / "Photos")
    QApplication.clipboard().setText("")
    window.btn_copy.click()
    assert QApplication.clipboard().text() == window.link


def test_the_address_is_shown_only_after_the_server_has_started(qapp, window, home, local_only, monkeypatch):
    monkeypatch.setattr(server, "server_started", lambda: False)
    window.folder_input.setText(str(home / "Photos"))
    window.start_server()
    for _ in range(10):
        qapp.processEvents()
        time.sleep(0.01)
    assert window.is_running
    assert window.url_label.text() == "Starting…"
    assert not window.btn_copy.isEnabled()
    assert window.code_label.text() == ""


def test_a_failed_start_shows_one_message_and_stays_stopped(window, home, bars, local_only, monkeypatch):
    def fail(port):
        raise OSError(48, "Address already in use")
    monkeypatch.setattr(server, "open_listen_socket", fail)
    window.folder_input.setText(str(home / "Photos"))

    window.start_server()

    assert [kind for kind, *_ in bars] == ["error"]
    assert not window.is_running and window.btn_toggle.isEnabled()
    assert window.status_label.text() == "Ready"
    assert access.code is None


def test_a_server_that_refuses_to_start_shows_one_message_and_stays_stopped(window, home, bars, local_only, monkeypatch):
    def refuse(sock):
        sock.close()
        raise RuntimeError("An earlier server is still shutting down.")
    monkeypatch.setattr(server, "start_server", refuse)
    window.folder_input.setText(str(home / "Photos"))

    window.start_server()

    assert [kind for kind, *_ in bars] == ["error"]
    assert not window.is_running and window.btn_toggle.isEnabled()
    assert access.code is None


def test_a_server_thread_that_dies_while_starting_shows_one_message(qapp, window, home, bars, local_only, monkeypatch):
    class Dead:
        def is_alive(self):
            return False
    monkeypatch.setattr(server, "start_server", lambda sock: (sock.close(), Dead())[1])
    window.folder_input.setText(str(home / "Photos"))

    window.start_server()
    wait_for(qapp, lambda: not window.is_running)

    assert [kind for kind, *_ in bars] == ["error"]
    assert window.btn_toggle.isEnabled()


# --- Stopping ---

def test_stop_shows_stopping_until_the_thread_has_ended(qapp, window, bars, monkeypatch):
    class Lingering:
        alive = True

        def is_alive(self):
            return self.alive

    lingering = Lingering()
    window.is_running = True
    window.server_thread = lingering
    monkeypatch.setattr(server, "stop_server", lambda: False)

    window.stop_server()

    assert window.status_label.text() == "Stopping…"
    assert not window.btn_toggle.isEnabled()
    assert window.is_running
    assert bars == []

    lingering.alive = False
    wait_for(qapp, lambda: not window.is_running)
    assert window.btn_toggle.isEnabled()
    assert window.status_label.text() == "Ready"
    assert [title for _, title, _ in bars] == ["Offline"]


def test_closing_the_window_stops_the_server(qapp, window, home, local_only):
    start(qapp, window, home / "Photos")
    thread = window.server_thread

    window.close()

    assert not thread.is_alive()
    assert not server.server_started()
    assert access.code is None
