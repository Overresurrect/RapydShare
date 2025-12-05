import sys
import os
import multiprocessing

def main():
    # 1. Force PyQt6
    os.environ["QT_API"] = "pyqt6"
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    os.environ["QT_SCALE_FACTOR_ROUNDING_POLICY"] = "PassThrough"

    # 2. Create Application Instance BEFORE importing widgets
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    # 3. Setup Utilities
    from src.utils import setup_logging_hack
    setup_logging_hack()

    # 4. Import GUI (Safe now because 'app' exists)
    from src.gui import launch_gui
    
    # 5. Launch Window
    # We assign it to 'window' so it doesn't get garbage collected
    window = launch_gui()

    # 6. Start Loop
    sys.exit(app.exec())

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()