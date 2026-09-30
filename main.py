import sys
import threading

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QApplication, QMessageBox
from ui.uimanager import MainWindow
from utils.logutils import get_logger

logger = get_logger(__name__)
_reporter = None


class ExceptionReporter(QObject):
    raised = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.raised.connect(self.show_error)

    @pyqtSlot(str)
    def show_error(self, message):
        QMessageBox.critical(None, 'Unexpected error', message)


def report_exception(exc_type, exc_value, traceback):
    logger.error('Unhandled exception', exc_info=(exc_type, exc_value, traceback))
    if QApplication.instance() is not None and _reporter is not None:
        _reporter.raised.emit(str(exc_value) or exc_type.__name__)


def install_exception_hooks():
    global _reporter
    _reporter = ExceptionReporter()
    sys.excepthook = report_exception
    threading.excepthook = lambda args: report_exception(args.exc_type, args.exc_value, args.exc_traceback)


def main():
    app = QApplication(sys.argv)
    install_exception_hooks()
    try:
        main_window = MainWindow()
        main_window.show()
    except BaseException:
        report_exception(*sys.exc_info())
        return 1
    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())
