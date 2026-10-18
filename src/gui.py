import sys
import os
from PyQt6.QtCore import Qt, QSize, QTimer, QSettings
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QWidget, QFileDialog, QApplication, QFrame, QLabel
)
from PyQt6.QtGui import QIcon, QFont, QPixmap

# Modern UI Components
from qfluentwidgets import (
    SubtitleLabel, BodyLabel, LineEdit, PushButton,
    SwitchButton, InfoBar, InfoBarPosition,
    StrongBodyLabel, CaptionLabel, TransparentToolButton,
    FluentIcon as FIF, setTheme, Theme, setThemeColor, TitleLabel
)

from src.access import access, format_code
from src.config import config
from src import server
from src.paths import refuse_share_folder
# Import our new QR code generator and the existing IP function
from src.utils import get_local_ip, generate_qr_code_pixmap

# A macOS .app starts with "/" as its working directory, so default to the home folder there
DEFAULT_DIR = os.getcwd() if sys.platform == "win32" else os.path.expanduser("~")

def ui_font(size, weight):
    # Segoe UI only exists on Windows; elsewhere use the system font
    family = "Segoe UI" if sys.platform == "win32" else QApplication.font().family()
    return QFont(family, size, weight)

class ServerLauncher(QWidget):
    def __init__(self, settings=None):
        super().__init__()
        self.setWindowTitle("RapydShare")
        self.settings = settings or QSettings("RapydShare", "RapydShare")

        if os.path.exists(config.ICON_PATH):
            self.setWindowIcon(QIcon(config.ICON_PATH))

        # 1. Window Size
        self.setFixedSize(680, 740)
        self.setStyleSheet("background-color: #202020; color: white;")

        self.is_running = False
        self.server_thread = None
        self.link = ""

        # --- Main Layout: HORIZONTAL ---
        self.main_h_layout = QHBoxLayout(self)
        self.main_h_layout.setContentsMargins(0, 0, 0, 0)
        self.main_h_layout.setSpacing(0)

        # --- LEFT PANEL: SERVER CONFIGURATION ---
        self.create_config_panel()

        # --- RIGHT PANEL: QR CODE DISPLAY ---
        self.create_qr_panel()

        # --- Add both panels to the main layout ---
        # The first widget added goes on the left.
        self.main_h_layout.addWidget(self.config_panel, 4) # Config panel on the LEFT
        self.main_h_layout.addWidget(self.qr_panel, 3)     # QR panel on the RIGHT


    def create_qr_panel(self):
        """Creates the right panel for displaying the QR code and server link."""
        self.qr_panel = QWidget()
        self.qr_panel.setStyleSheet("background-color: #2c2c2c; border-radius: 0px;")
        
        qr_layout = QVBoxLayout(self.qr_panel)
        qr_layout.setContentsMargins(20, 30, 20, 30)
        qr_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_layout.setSpacing(15)

        # QR Code Title
        qr_title = TitleLabel("Scan to connect", self.qr_panel)
        qr_layout.addWidget(qr_title, 0, Qt.AlignmentFlag.AlignHCenter)

        # QR Code Image Holder
        self.qr_code_label = QLabel("Server is offline", self.qr_panel)
        self.qr_code_label.setFixedSize(220, 220)
        self.qr_code_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_code_label.setStyleSheet("background-color: #3a3a3a; border-radius: 8px; color: #888888;")
        qr_layout.addWidget(self.qr_code_label)

        # URL Link Label
        self.url_label = CaptionLabel("Ready to start", self.qr_panel)
        self.url_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.url_label.setWordWrap(True)
        qr_layout.addWidget(self.url_label)

        # The access code, large, and the button that copies the full link
        self.code_label = QLabel("", self.qr_panel)
        self.code_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code_label.setFont(ui_font(30, QFont.Weight.Bold))
        self.code_label.setStyleSheet("color: #60CDFF; letter-spacing: 3px;")
        qr_layout.addWidget(self.code_label)

        self.btn_copy = PushButton("Copy link", self.qr_panel)
        self.btn_copy.setEnabled(False)
        self.btn_copy.clicked.connect(self.copy_link)
        qr_layout.addWidget(self.btn_copy, 0, Qt.AlignmentFlag.AlignHCenter)

        qr_layout.addStretch()

    def create_config_panel(self):
        """Creates the left panel with all the server settings."""
        self.config_panel = QWidget()
        
        self.v_layout = QVBoxLayout(self.config_panel)
        self.v_layout.setContentsMargins(25, 30, 25, 30)
        self.v_layout.setSpacing(10)

        # --- HEADING SECTION ---
        self.title_label = SubtitleLabel("Server Configuration", self)
        self.title_label.setFont(ui_font(20, QFont.Weight.Bold))
        self.v_layout.addWidget(self.title_label)
        self.v_layout.addSpacing(5)

        # --- SELECT FOLDER SECTION ---
        self.v_layout.addLayout(
            self.create_label_with_help("Shared Folder", "Select the folder containing the files you want to share.")
        )
        h_folder = QHBoxLayout()
        h_folder.setSpacing(8)
        self.folder_input = LineEdit(self)
        self.folder_input.setPlaceholderText("Choose a folder to share…")
        remembered = self.settings.value("folder", "")
        if remembered and os.path.isdir(remembered):
            self.folder_input.setText(remembered)
        self.folder_input.setFixedHeight(35)
        self.btn_browse = PushButton("Select", self)
        self.btn_browse.setFixedWidth(75)
        self.btn_browse.setFixedHeight(35)
        self.btn_browse.clicked.connect(self.browse_folder)
        h_folder.addWidget(self.folder_input)
        h_folder.addWidget(self.btn_browse)
        self.v_layout.addLayout(h_folder)

        # --- PORT SECTION ---
        self.v_layout.addSpacing(5)
        self.v_layout.addLayout(
            self.create_label_with_help("Port", "Network port to listen on. Default is 8000. Change if busy.")
        )
        self.port_input = LineEdit(self)
        self.port_input.setText("8000")
        self.port_input.setFixedHeight(35)
        self.v_layout.addWidget(self.port_input)
        self.v_layout.addSpacing(5)

        # --- ACCESS CODE SECTION ---
        h_code_header = QHBoxLayout()
        h_code_header.setSpacing(5)
        lbl_code = StrongBodyLabel("Require access code", self)
        btn_help_code = TransparentToolButton(FIF.INFO, self)
        btn_help_code.setFixedSize(20, 20)
        btn_help_code.setIconSize(QSize(12, 12))
        btn_help_code.setToolTip("Visitors must enter the code shown here before they can see your files.")
        btn_help_code.setStyleSheet("TransparentToolButton { border: none; background: transparent; color: #cccccc; }")
        self.switch_code = SwitchButton(parent=self)
        self.switch_code.setChecked(True)
        self.switch_code.checkedChanged.connect(self.toggle_code)
        h_code_header.addWidget(lbl_code)
        h_code_header.addWidget(btn_help_code)
        h_code_header.addStretch(1)
        h_code_header.addWidget(self.switch_code)
        self.v_layout.addLayout(h_code_header)

        self.note_label = CaptionLabel("Not encrypted. Use on networks you trust.", self)
        self.note_label.setStyleSheet("color: #aaaaaa;")
        self.v_layout.addWidget(self.note_label)
        self.v_layout.addSpacing(15)

        # --- UPLOAD SECTION ---
        h_upload_header = QHBoxLayout()
        h_upload_header.setSpacing(5)
        lbl_upload = StrongBodyLabel("Allow Uploads", self)
        btn_help_upload = TransparentToolButton(FIF.INFO, self)
        btn_help_upload.setFixedSize(20, 20)
        btn_help_upload.setIconSize(QSize(12, 12))
        btn_help_upload.setToolTip("Let clients upload files into the folder you choose below.")
        btn_help_upload.setStyleSheet("TransparentToolButton { border: none; background: transparent; color: #cccccc; }")
        self.switch_upload = SwitchButton(parent=self)
        self.switch_upload.checkedChanged.connect(self.toggle_upload)
        h_upload_header.addWidget(lbl_upload)
        h_upload_header.addWidget(btn_help_upload)
        h_upload_header.addStretch(1)
        h_upload_header.addWidget(self.switch_upload)
        self.v_layout.addLayout(h_upload_header)

        h_upload_folder = QHBoxLayout()
        h_upload_folder.setSpacing(8)
        self.upload_folder_input = LineEdit(self)
        self.upload_folder_input.setPlaceholderText("Select a folder to receive uploads...")
        self.upload_folder_input.setEnabled(False)
        self.upload_folder_input.setFixedHeight(35)
        self.btn_browse_upload = PushButton("Select", self)
        self.btn_browse_upload.setFixedWidth(75)
        self.btn_browse_upload.setFixedHeight(35)
        self.btn_browse_upload.setEnabled(False)
        self.btn_browse_upload.clicked.connect(self.browse_upload_folder)
        h_upload_folder.addWidget(self.upload_folder_input)
        h_upload_folder.addWidget(self.btn_browse_upload)
        self.v_layout.addLayout(h_upload_folder)
        self.v_layout.addSpacing(15)

        # --- SERVER BUTTON ---
        h_btn_layout = QHBoxLayout()
        h_btn_layout.addStretch()
        self.btn_toggle = PushButton("Start Server", self)
        self.btn_toggle.setFixedSize(195, 52)
        self.btn_toggle.setFont(ui_font(12, QFont.Weight.Bold))
        self.btn_toggle.clicked.connect(self.toggle_server_state)
        h_btn_layout.addWidget(self.btn_toggle)
        h_btn_layout.addStretch()
        self.v_layout.addLayout(h_btn_layout)
        self.apply_button_style(started=False)

        # Status
        self.status_label = CaptionLabel("Ready", self)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.status_label.setStyleSheet("color: #888888; margin-top: 5px;")
        self.v_layout.addWidget(self.status_label)
        self.v_layout.addStretch(1)

    def create_label_with_help(self, text, help_text):
        layout = QHBoxLayout()
        layout.setSpacing(5)
        label = StrongBodyLabel(text, self)
        btn_help = TransparentToolButton(FIF.INFO, self)
        btn_help.setFixedSize(20, 20)
        btn_help.setIconSize(QSize(12, 12))
        btn_help.setToolTip(help_text)
        btn_help.setStyleSheet("TransparentToolButton { border: none; background: transparent; color: #cccccc; }")
        layout.addWidget(label)
        layout.addWidget(btn_help)
        layout.addStretch(1)
        return layout

    def apply_button_style(self, started):
        if started:
            self.btn_toggle.setText("Stop Server")
            self.btn_toggle.setStyleSheet("PushButton { background-color: #454545; color: white; border: none; border-radius: 8px; } PushButton:hover { background-color: #505050; } PushButton:pressed { background-color: #3a3a3a; }")
        else:
            self.btn_toggle.setText("Start Server")
            self.btn_toggle.setStyleSheet("PushButton { background-color: #60CDFF; color: black; border: none; border-radius: 8px; } PushButton:hover { background-color: #70d5ff; } PushButton:pressed { background-color: #50b0e0; }")

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if not folder: return
        self.folder_input.setText(folder)
        problem = refuse_share_folder(folder)
        if problem:
            self.show_error("Error", problem)
        else:
            self.settings.setValue("folder", folder)

    def toggle_code(self, checked):
        if not checked:
            self.show_warning("Warning", "Anyone on this Wi-Fi can open your shared folder.")

    def toggle_upload(self, checked):
        self.upload_folder_input.setEnabled(checked)
        self.btn_browse_upload.setEnabled(checked)

    def browse_upload_folder(self):
        start_dir = self.upload_folder_input.text() or self.folder_input.text() or DEFAULT_DIR
        folder = QFileDialog.getExistingDirectory(self, "Select Upload Folder", start_dir)
        if folder:
            self.upload_folder_input.setText(folder)

    def toggle_server_state(self):
        if not self.is_running:
            self.start_server()
        else:
            self.stop_server()

    def start_server(self):
        folder = self.folder_input.text().strip()
        problem = refuse_share_folder(folder)
        if problem:
            self.show_error("Error", problem)
            return
        try:
            port = server.parse_port(self.port_input.text())
        except ValueError as e:
            self.show_error("Error", str(e))
            return

        upload_dir = ""
        if self.switch_upload.isChecked():
            upload_dir = self.upload_folder_input.text().strip()
            if not upload_dir or not os.path.isdir(upload_dir):
                self.show_error("Error", "Upload folder does not exist.")
                return
            try:
                shared_real = os.path.realpath(folder)
                upload_real = os.path.realpath(upload_dir)
                common = os.path.commonpath([shared_real, upload_real])
                if os.path.normcase(common) != os.path.normcase(shared_real):
                    self.show_warning("Warning", "Upload folder is outside the shared folder. Clients won't see uploads.")
            except ValueError:
                self.show_warning("Warning", "Upload folder is on a different drive than the shared folder.")

        try:
            sock = server.open_listen_socket(port)
        except OSError as e:
            self.show_error("Error", f"Couldn't use port {port}: {e.strerror or e}")
            return

        config.ROOT_DIR = folder
        config.PORT = port
        config.ALLOW_UPLOAD = bool(upload_dir)
        config.UPLOAD_DIR = upload_dir
        config.REQUIRE_CODE = self.switch_code.isChecked()
        code = access.start(config.REQUIRE_CODE)
        try:
            self.server_thread = server.start_server(sock)
        except (RuntimeError, OSError):
            access.stop()
            self.show_error("Error", "The server couldn't start. If you just stopped it, wait a moment and try again.")
            return

        self.settings.setValue("folder", folder)
        self.set_inputs_enabled(False)
        self.folder_input.setReadOnly(True)
        self.is_running = True
        self.apply_button_style(started=True)
        self.status_label.setText("Starting...")
        self.url_label.setText("Starting…")
        self.wait_until_started(self.server_thread, code)

    def wait_until_started(self, thread, code):
        """Shows the address once uvicorn has started, or stops if its thread ended first."""
        if thread is not self.server_thread: return
        if server.server_started():
            self.show_online(code)
        elif thread.is_alive():
            QTimer.singleShot(50, lambda: self.wait_until_started(thread, code))
        else:
            server.stop_server()
            self.show_offline()
            self.show_error("Error", "The server couldn't start.")

    def show_online(self, code):
        ip = get_local_ip()
        self.link = f"http://{ip}:{config.PORT}" + (f"/{code}" if code else "")
        self.status_label.setText(f"Running at: {self.link}")
        self.code_label.setText(format_code(code) if code else "")
        self.btn_copy.setEnabled(True)

        # --- Generate and display QR code ---
        try:
            qr_pixmap = generate_qr_code_pixmap(self.link, size=220)
            self.qr_code_label.setPixmap(qr_pixmap)
            self.url_label.setText(self.link)
        except Exception as e:
            self.qr_code_label.setText("QR Error")
            print(f"QR Generation Failed: {e}")

        self.copy_link()
        self.show_success("Online", "Server running. Copied link to clipboard.")

    def copy_link(self):
        QApplication.clipboard().setText(self.link)

    def stop_server(self):
        thread = self.server_thread
        if server.stop_server():
            self.show_offline()
            self.show_info("Offline", "Server has been stopped.")
            return
        self.btn_toggle.setEnabled(False)
        self.status_label.setText("Stopping…")
        self.wait_until_stopped(thread)

    def wait_until_stopped(self, thread):
        """Keeps showing Stopping… until the server thread has ended, then goes offline."""
        if thread is not self.server_thread: return
        if thread.is_alive():
            QTimer.singleShot(100, lambda: self.wait_until_stopped(thread))
        else:
            self.show_offline()
            self.show_info("Offline", "Server has been stopped.")

    def show_offline(self):
        self.server_thread = None
        self.is_running = False
        self.link = ""
        self.apply_button_style(started=False)
        self.btn_toggle.setEnabled(True)
        self.set_inputs_enabled(True)
        self.folder_input.setReadOnly(False)
        self.status_label.setText("Ready")

        # --- Reset QR code panel ---
        self.qr_code_label.setText("Server is offline")
        self.qr_code_label.setPixmap(QPixmap())
        self.url_label.setText("Ready to start")
        self.code_label.setText("")
        self.btn_copy.setEnabled(False)

    def closeEvent(self, event):
        server.stop_server()
        self.server_thread = None
        super().closeEvent(event)

    def set_inputs_enabled(self, enable):
        self.btn_browse.setEnabled(enable)
        self.port_input.setEnabled(enable)
        self.switch_code.setEnabled(enable)
        self.switch_upload.setEnabled(enable)
        upload_on = enable and self.switch_upload.isChecked()
        self.upload_folder_input.setEnabled(upload_on)
        self.btn_browse_upload.setEnabled(upload_on)

    def show_success(self, title, msg):
        InfoBar.success(title=title, content=msg, orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=3000, parent=self)

    def show_warning(self, title, msg):
        InfoBar.warning(title=title, content=msg, orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=5000, parent=self)

    def show_error(self, title, msg):
        InfoBar.error(title=title, content=msg, orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=5000, parent=self)

    def show_info(self, title, msg):
        InfoBar.info(title=title, content=msg, orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=3000, parent=self)

def launch_gui():
    setTheme(Theme.DARK)
    setThemeColor('#60CDFF')
    w = ServerLauncher()
    w.show()
    return w