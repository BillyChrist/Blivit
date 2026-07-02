"""Thread-safe log delivery from background serial threads into the Qt GUI."""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal


class UiLogBridge(QObject):
    """Emit log lines from any thread; Qt queues them onto the GUI thread."""

    message = pyqtSignal(str)
    avionics_event = pyqtSignal(str)
    avionics_download_done = pyqtSignal(str)
    avionics_download_failed = pyqtSignal(str)
    serial_connect_done = pyqtSignal(bool, str, str)

    def emit_serial_connect_done(self, ok: bool, error: str, reason: str) -> None:
        self.serial_connect_done.emit(ok, error, reason)

    def write(self, text: str) -> None:
        self.message.emit(text)

    def emit_avionics_event(self, line: str) -> None:
        self.avionics_event.emit(line)

    def emit_download_done(self, path: str) -> None:
        self.avionics_download_done.emit(path)

    def emit_download_failed(self, message: str) -> None:
        self.avionics_download_failed.emit(message)
