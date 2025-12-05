import sys
import os
import threading
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QWidget, QFileDialog, QApplication, QFrame
)
from PyQt6.QtGui import QIcon, QFont

# Modern UI Components
from qfluentwidgets import (
    SubtitleLabel, BodyLabel, LineEdit, PushButton, 
    SwitchButton, InfoBar, InfoBarPosition, 
    StrongBodyLabel, CaptionLabel, TransparentToolButton, 
    FluentIcon as FIF, setTheme, Theme, setThemeColor
)

from src.config import config
from src.server import run_server, stop_server_logic
from src.utils import get_local_ip

class ServerLauncher(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RapydShare")
        
        if os.path.exists(config.ICON_PATH):
            self.setWindowIcon(QIcon(config.ICON_PATH))
            
        # 1. Window Size - 380 x 600
        self.setFixedSize(380, 600)
        self.setStyleSheet("background-color: #202020; color: white;")

        self.is_running = False
        self.server_thread = None

        # Main Layout
        self.v_layout = QVBoxLayout(self)
        self.v_layout.setContentsMargins(25, 30, 25, 30)
        self.v_layout.setSpacing(10)

        # --- HEADING SECTION ---
        self.title_label = SubtitleLabel("Server Configuration", self)
        self.title_label.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.v_layout.addWidget(self.title_label)
        
        self.v_layout.addSpacing(5)

        # --- SELECT FOLDER SECTION ---
        # Label with Tooltip
        self.v_layout.addLayout(
            self.create_label_with_help("Shared Folder", "Select the folder containing the files you want to share.")
        )
        
        h_folder = QHBoxLayout()
        h_folder.setSpacing(8)
        
        # File Directory Input
        self.folder_input = LineEdit(self)
        self.folder_input.setText(os.getcwd())
        self.folder_input.setPlaceholderText("Enter folder path...")
        self.folder_input.setReadOnly(False)
        self.folder_input.setFixedHeight(35)
        
        # Select Button
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

        # --- AUTHENTICATION SECTION ---
        h_auth_header = QHBoxLayout()
        h_auth_header.setSpacing(5)
        
        # Label
        lbl_auth = StrongBodyLabel("Authentication", self)
        h_auth_header.addWidget(lbl_auth)
        
        # Help Icon
        btn_help_auth = TransparentToolButton(FIF.INFO, self)
        btn_help_auth.setFixedSize(20, 20)
        btn_help_auth.setIconSize(QSize(12, 12))
        btn_help_auth.setToolTip("Require users to enter a username and password to access files.")
        btn_help_auth.setStyleSheet("TransparentToolButton { border: none; background: transparent; color: #cccccc; }")
        h_auth_header.addWidget(btn_help_auth)
        
        h_auth_header.addStretch(1)
        
        # Switch
        self.switch_auth = SwitchButton(parent=self)
        self.switch_auth.checkedChanged.connect(self.toggle_auth)
        h_auth_header.addWidget(self.switch_auth)
        
        self.v_layout.addLayout(h_auth_header)

        # Inputs
        self.v_layout.addWidget(BodyLabel("Username", self))
        self.user_input = LineEdit(self)
        self.user_input.setPlaceholderText("admin")
        self.user_input.setText("admin")
        self.user_input.setEnabled(False)
        self.user_input.setFixedHeight(35)
        self.v_layout.addWidget(self.user_input)

        self.v_layout.addWidget(BodyLabel("Password", self))
        self.pass_input = LineEdit(self)
        self.pass_input.setPlaceholderText("Password")
        self.pass_input.setText("1234")
        self.pass_input.setEchoMode(LineEdit.EchoMode.Password)
        self.pass_input.setEnabled(False)
        self.pass_input.setFixedHeight(35)
        self.v_layout.addWidget(self.pass_input)

        # Spacer
        self.v_layout.addSpacing(25)

        # --- SERVER BUTTON ---
        h_btn_layout = QHBoxLayout()
        h_btn_layout.addStretch()
        
        self.btn_toggle = PushButton("Start Server", self)
        self.btn_toggle.setFixedSize(195, 52)
        self.btn_toggle.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
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
        """Helper to create a Label + Info Icon row"""
        layout = QHBoxLayout()
        layout.setSpacing(5)
        
        label = StrongBodyLabel(text, self)
        layout.addWidget(label)
        
        btn_help = TransparentToolButton(FIF.INFO, self)
        btn_help.setFixedSize(20, 20)
        btn_help.setIconSize(QSize(12, 12))
        btn_help.setToolTip(help_text)
        # Ensure it looks clean on dark bg
        btn_help.setStyleSheet("TransparentToolButton { border: none; background: transparent; color: #cccccc; }")
        
        layout.addWidget(btn_help)
        layout.addStretch(1)
        return layout

    def apply_button_style(self, started):
        if started:
            # STOP State: #454545
            self.btn_toggle.setText("Stop Server")
            self.btn_toggle.setStyleSheet("""
                PushButton {
                    background-color: #454545;
                    color: white;
                    border: none;
                    border-radius: 8px;
                }
                PushButton:hover { background-color: #505050; }
                PushButton:pressed { background-color: #3a3a3a; }
            """)
        else:
            # START State: #60CDFF
            self.btn_toggle.setText("Start Server")
            self.btn_toggle.setStyleSheet("""
                PushButton {
                    background-color: #60CDFF;
                    color: black;
                    border: none;
                    border-radius: 8px;
                }
                PushButton:hover { background-color: #70d5ff; }
                PushButton:pressed { background-color: #50b0e0; }
            """)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder: self.folder_input.setText(folder)

    def toggle_auth(self, checked):
        self.user_input.setEnabled(checked)
        self.pass_input.setEnabled(checked)

    def toggle_server_state(self):
        if not self.is_running:
            self.start_server()
        else:
            self.stop_server()

    def start_server(self):
        config.ROOT_DIR = self.folder_input.text()
        try: config.PORT = int(self.port_input.text())
        except: return
        config.USE_AUTH = self.switch_auth.isChecked()
        config.USERNAME = self.user_input.text()
        config.PASSWORD = self.pass_input.text()

        if not os.path.exists(config.ROOT_DIR):
            self.show_info("Error", "Directory does not exist")
            return

        self.set_inputs_enabled(False)
        self.folder_input.setReadOnly(True)
        
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        
        self.is_running = True
        self.apply_button_style(started=True)
        
        ip = get_local_ip()
        link = f"http://{ip}:{config.PORT}"
        self.status_label.setText(f"Running at: {link}")
        
        QApplication.clipboard().setText(link)
        self.show_success("Online", f"Copied: {link}")

    def stop_server(self):
        stop_server_logic()
        
        self.is_running = False
        self.apply_button_style(started=False)
        self.set_inputs_enabled(True)
        self.folder_input.setReadOnly(False)
        self.status_label.setText("Ready")
        
        self.show_info("Offline", "Server has been stopped.")

    def set_inputs_enabled(self, enable):
        self.btn_browse.setEnabled(enable)
        self.port_input.setEnabled(enable)
        self.switch_auth.setEnabled(enable)
        if enable and self.switch_auth.isChecked():
            self.user_input.setEnabled(True)
            self.pass_input.setEnabled(True)
        else:
            self.user_input.setEnabled(False)
            self.pass_input.setEnabled(False)

    def show_success(self, title, msg):
        InfoBar.success(title=title, content=msg, orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=3000, parent=self)

    def show_info(self, title, msg):
        InfoBar.info(title=title, content=msg, orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=3000, parent=self)

def launch_gui():
    setTheme(Theme.DARK)
    setThemeColor('#60CDFF')
    w = ServerLauncher()
    w.show()
    return w