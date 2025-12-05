import os
import sys

# Force PyQt6
os.environ["QT_API"] = "pyqt6"

from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel
from qfluentwidgets import PrimaryPushButton, setTheme, Theme

if __name__ == "__main__":
    print("1. Creating Application...")
    app = QApplication(sys.argv)
    
    print("2. Setting Theme...")
    setTheme(Theme.DARK)
    
    print("3. Creating Window...")
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.addWidget(QLabel("If you see this, the UI library works."))
    layout.addWidget(PrimaryPushButton("Click Me"))
    
    w.show()
    print("4. Executing...")
    sys.exit(app.exec())