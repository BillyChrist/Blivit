"""COM port, link, and heartbeat status panel."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)


class _StatusLed(QLabel):
    def set_state(self, state: str) -> None:
        colors = {
            "live": ("#44dd66", "LIVE"),
            "waiting": ("#ffaa00", "WAITING"),
            "stale": ("#ff8844", "STALE"),
            "error": ("#ff4444", "ERROR"),
            "offline": ("#666666", "OFFLINE"),
        }
        color, label = colors.get(state, colors["offline"])
        self.setText(f"● {label}")
        self.setStyleSheet(f"color: {color}; font-weight: bold;")


class CommsStatusPanel(QFrame):
    """Link status and logging controls beside the attitude plot."""

    logging_toggled = pyqtSignal()
    avionics_log_start = pyqtSignal()
    avionics_log_stop = pyqtSignal()
    avionics_log_download = pyqtSignal()
    avionics_log_clear = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("commsStatus")
        self.setStyleSheet(
            """
            QFrame#commsStatus {
                background-color: #1a1a1a;
                border: 1px solid #3a3a3a;
                border-radius: 6px;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        title = QLabel("COMS")
        title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #888888; border: none;")
        root.addWidget(title)

        btn_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        status_font = QFont("Consolas", 9)

        self._log_btn = QPushButton("Start Logging")
        self._log_btn.setFont(btn_font)
        self._log_btn.setMinimumHeight(36)
        self._log_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._log_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._log_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #2a4a2a;
                color: #e0e0e0;
                border: 1px solid #446644;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover { background-color: #355a35; }
            """
        )
        self._log_btn.clicked.connect(self.logging_toggled.emit)
        root.addWidget(self._log_btn)

        self._log_status = QLabel("Not recording")
        self._log_status.setFont(status_font)
        self._log_status.setStyleSheet("color: #777777; border: none;")
        self._log_status.setWordWrap(True)
        root.addWidget(self._log_status)

        avionics_label = QLabel("Avionics Log")
        avionics_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        avionics_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avionics_label.setStyleSheet("color: #aaaaaa; border: none; padding-top: 4px;")
        root.addWidget(avionics_label)

        btn_style = """
            QPushButton {
                background-color: #2a3a4a;
                color: #e0e0e0;
                border: 1px solid #445566;
                border-radius: 4px;
                padding: 8px 12px;
            }
            QPushButton:hover { background-color: #354a5a; }
            QPushButton:disabled {
                background-color: #222222;
                color: #555555;
                border-color: #333333;
            }
        """
        self._avionics_start_btn = QPushButton("Remote Record")
        self._avionics_stop_btn = QPushButton("Stop Recording")
        self._avionics_download_btn = QPushButton("Download Log")
        self._avionics_clear_btn = QPushButton("Clear Avionics Log")
        clear_btn_style = """
            QPushButton {
                background-color: #3a2a2a;
                color: #e0e0e0;
                border: 1px solid #664444;
                border-radius: 4px;
                padding: 8px 12px;
            }
            QPushButton:hover { background-color: #4a3333; }
            QPushButton:disabled {
                background-color: #222222;
                color: #555555;
                border-color: #333333;
            }
        """
        for btn in (self._avionics_start_btn, self._avionics_stop_btn, self._avionics_download_btn):
            btn.setFont(btn_font)
            btn.setMinimumHeight(36)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(btn_style)
            root.addWidget(btn)
        self._avionics_clear_btn.setFont(btn_font)
        self._avionics_clear_btn.setMinimumHeight(36)
        self._avionics_clear_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._avionics_clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._avionics_clear_btn.setStyleSheet(clear_btn_style)
        root.addWidget(self._avionics_clear_btn)
        self._avionics_start_btn.clicked.connect(self.avionics_log_start.emit)
        self._avionics_stop_btn.clicked.connect(self.avionics_log_stop.emit)
        self._avionics_download_btn.clicked.connect(self.avionics_log_download.emit)
        self._avionics_clear_btn.clicked.connect(self.avionics_log_clear.emit)
        self._avionics_stop_btn.setEnabled(False)

        self._avionics_status = QLabel("Idle")
        self._avionics_status.setFont(status_font)
        self._avionics_status.setStyleSheet("color: #777777; border: none;")
        self._avionics_status.setWordWrap(True)
        root.addWidget(self._avionics_status)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)

        font_label = QFont("Segoe UI", 9)
        font_value = QFont("Consolas", 10)

        rows = [
            ("port", "COM Port"),
            ("mode", "Mode"),
            ("heartbeat", "Heartbeat"),
            ("uptime", "Avionics Uptime"),
            ("age", "Last Update"),
        ]
        self._values: dict[str, QLabel] = {}

        row = 0
        for key, label_text in rows:
            name = QLabel(label_text)
            name.setFont(font_label)
            name.setStyleSheet("color: #777777; border: none;")
            value = QLabel("—")
            value.setFont(font_value)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            value.setStyleSheet("color: #e8e8e8; border: none;")
            grid.addWidget(name, row, 0)
            grid.addWidget(value, row, 1)
            self._values[key] = value
            row += 1

        link_name = QLabel("Link")
        link_name.setFont(font_label)
        link_name.setStyleSheet("color: #777777; border: none;")
        self._link_led = _StatusLed("● OFFLINE")
        self._link_led.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self._link_led.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(link_name, row, 0)
        grid.addWidget(self._link_led, row, 1)
        self._error_label = QLabel("")
        self._error_label.setFont(font_value)
        self._error_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet("color: #ff6666; border: none;")
        self._error_label.hide()
        grid.addWidget(self._error_label, row + 1, 0, 1, 2)

        root.addLayout(grid)
        root.addStretch()

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumWidth(300)

    def update_status(
        self,
        *,
        port: str,
        baud: int,
        mode: str,
        link_state: str,
        sequence: Optional[int] = None,
        uptime_ms: Optional[int] = None,
        age_ms: Optional[float] = None,
        source: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        self._values["port"].setText(f"{port} @ {baud}")
        self._values["mode"].setText(mode)

        if error:
            self._link_led.set_state("error")
            self._link_led.hide()
            self._error_label.setText(error)
            self._error_label.show()
        else:
            self._link_led.set_state(link_state)
            self._link_led.show()
            self._error_label.hide()

        if sequence is not None:
            src = f" ({source})" if source else ""
            self._values["heartbeat"].setText(f"seq {sequence}{src}")
        else:
            self._values["heartbeat"].setText("—")

        if uptime_ms is not None:
            self._values["uptime"].setText(f"{uptime_ms / 1000:.1f} s")
        else:
            self._values["uptime"].setText("—")

        if age_ms is not None:
            if age_ms < 1000:
                self._values["age"].setText(f"{age_ms:.0f} ms ago")
            else:
                self._values["age"].setText(f"{age_ms / 1000:.1f} s ago")
        else:
            self._values["age"].setText("—")

    def set_logging_state(self, active: bool, filepath: str = "") -> None:
        if active:
            self._log_btn.setText("Stop Logging")
            self._log_btn.setStyleSheet(
                """
                QPushButton {
                    background-color: #4a2020;
                    color: #ffe0e0;
                    border: 1px solid #884444;
                    border-radius: 4px;
                    padding: 8px 16px;
                }
                QPushButton:hover { background-color: #5a2828; }
                """
            )
            name = filepath.replace("\\", "/").split("/")[-1] if filepath else "recording"
            self._log_status.setText(name)
            self._log_status.setStyleSheet("color: #44dd66; border: none;")
        else:
            self._log_btn.setText("Start Logging")
            self._log_btn.setStyleSheet(
                """
                QPushButton {
                    background-color: #2a4a2a;
                    color: #e0e0e0;
                    border: 1px solid #446644;
                    border-radius: 4px;
                    padding: 8px 16px;
                }
                QPushButton:hover { background-color: #355a35; }
                """
            )
            self._log_status.setText("Not recording")
            self._log_status.setStyleSheet("color: #777777; border: none;")

    def set_avionics_log_state(self, state: str, detail: str = "") -> None:
        """Update avionics onboard log controls: idle | recording | downloading."""
        if state == "recording":
            self._avionics_start_btn.setEnabled(False)
            self._avionics_stop_btn.setEnabled(True)
            self._avionics_download_btn.setEnabled(False)
            self._avionics_clear_btn.setEnabled(False)
            self._avionics_status.setText(detail or "Recording remotely…")
            self._avionics_status.setStyleSheet("color: #44dd66; border: none;")
        elif state == "downloading":
            self._avionics_start_btn.setEnabled(False)
            self._avionics_stop_btn.setEnabled(False)
            self._avionics_download_btn.setEnabled(False)
            self._avionics_clear_btn.setEnabled(False)
            self._avionics_status.setText(detail or "Downloading…")
            self._avionics_status.setStyleSheet("color: #ffaa00; border: none;")
        else:
            self._avionics_start_btn.setEnabled(True)
            self._avionics_stop_btn.setEnabled(False)
            self._avionics_download_btn.setEnabled(True)
            self._avionics_clear_btn.setEnabled(True)
            self._avionics_status.setText(detail or "Idle")
            self._avionics_status.setStyleSheet("color: #777777; border: none;")
