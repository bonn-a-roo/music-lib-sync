import sys

# Reconfigure stdout/stderr to UTF-8 before anything else so Unicode
# characters in playlist names (etc.) don't crash the console logger.
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from PyQt5.QtWidgets import QApplication
from ui.uimanager import MainWindow


def main():
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
