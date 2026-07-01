"""Main avionics-style ground station window."""

from __future__ import annotations

import sys
import threading
import time
import traceback
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QMouseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from gui.attitude_indicator import AttitudeDisplay
from gui.flight_analytics import FlightAnalyticsTab
from gui.log_bridge import UiLogBridge
from serial.tools import list_ports
from config import (
    DEFAULT_BAUD_RATES,
    GUI_REFRESH_MS,
    SERIAL_RECONNECT_COOLDOWN_S,
    SERIAL_RECONNECT_POLL_MS,
    SERIAL_STALE_RECONNECT_MS,
    STATUS_LOG_INTERVAL_MS,
    load_gui_settings,
    save_gui_settings,
)
from ground_station import GroundStation
from telemetry import TelemetrySnapshot


class _ConsoleHeader(QFrame):
    """Top bar of the console — drag vertically to resize the log panel."""

    def __init__(self, splitter: QSplitter, parent=None) -> None:
        super().__init__(parent)
        self._splitter = splitter
        self._drag_y: float | None = None
        self._sizes: list[int] = []

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_y = event.globalPosition().y()
            self._sizes = self._splitter.sizes()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_y is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta = int(event.globalPosition().y() - self._drag_y)
            upper = self._sizes[0] + delta
            lower = self._sizes[1] - delta
            min_upper = self._splitter.widget(0).minimumHeight()
            min_lower = self._splitter.widget(1).minimumHeight()
            if upper >= min_upper and lower >= min_lower:
                self._splitter.setSizes([upper, lower])
                self._drag_y = event.globalPosition().y()
                self._sizes = self._splitter.sizes()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_y = None
        super().mouseReleaseEvent(event)


class DataPanel(QGroupBox):
    _ROW_HEIGHT = 26

    def __init__(self, title: str, rows: list[tuple[str, str]], parent=None) -> None:
        super().__init__(title, parent)
        self._labels: dict[str, QLabel] = {}
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        inner = QWidget()
        layout = QGridLayout(inner)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setVerticalSpacing(6)
        layout.setHorizontalSpacing(12)
        layout.setColumnStretch(1, 1)

        font_label = QFont("Segoe UI", 9)
        font_value = QFont("Consolas", 11)

        for row, (key, label_text) in enumerate(rows):
            name = QLabel(label_text)
            name.setFont(font_label)
            name.setStyleSheet("color: #999999;")
            name.setMinimumHeight(self._ROW_HEIGHT)
            value = QLabel("—")
            value.setFont(font_value)
            value.setMinimumHeight(self._ROW_HEIGHT)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            value.setStyleSheet("color: #e8e8e8;")
            layout.addWidget(name, row, 0)
            layout.addWidget(value, row, 1)
            self._labels[key] = value

        inner.setMinimumHeight(len(rows) * self._ROW_HEIGHT + max(0, len(rows) - 1) * 6 + 8)
        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 12, 8, 8)
        outer.addWidget(scroll)

    def set_value(self, key: str, text: str, *, color: Optional[str] = None) -> None:
        label = self._labels[key]
        label.setText(text)
        if color:
            label.setStyleSheet(f"color: {color};")
        else:
            label.setStyleSheet("color: #e8e8e8;")


class GroundStationWindow(QMainWindow):
    def __init__(
        self,
        station: GroundStation,
        *,
        log_path: Optional[str] = None,
    ) -> None:
        super().__init__()
        self._station = station
        self._log_path = log_path
        self._last_seq = 0
        self._serial_error: Optional[str] = None
        self._startup_complete = False
        self._first_telemetry_logged = False
        self._startup_attempts = 0
        self._max_startup_attempts = 3
        self._stale_since: float | None = None
        self._last_reconnect_attempt = 0.0
        self._avionics_download_ui_active = False
        self._timestamp_record_active = False
        self._avionics_recording = False
        self._gui_settings = load_gui_settings()
        self._setup_port_combo: QComboBox | None = None
        self._setup_baud_combo: QComboBox | None = None
        self._setup_apply_btn: QPushButton | None = None
        self._reconnect_btn: QPushButton | None = None

        self.setWindowTitle("Blivit Ground Station")
        self.resize(1100, 720)
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background-color: #121212; color: #e0e0e0; }
            QGroupBox {
                border: 1px solid #333333;
                border-radius: 4px;
                margin-top: 10px;
                font-weight: bold;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QPlainTextEdit {
                background-color: #0d0d0d;
                color: #9cdcfe;
                border: 1px solid #333333;
                font-family: Consolas;
                font-size: 10pt;
            }
            QSplitter::handle:vertical {
                background-color: #2a2a2a;
                height: 8px;
                margin: 0 4px;
                border-top: 1px solid #444444;
                border-bottom: 1px solid #444444;
            }
            QSplitter::handle:vertical:hover {
                background-color: #3d3d3d;
            }
            QFrame#logHeader {
                background-color: #1a1a1a;
                border: 1px solid #333333;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabWidget::pane {
                border: 1px solid #333333;
                background-color: #121212;
            }
            QTabBar::tab {
                background-color: #1a1a1a;
                color: #888888;
                padding: 8px 18px;
                border: 1px solid #333333;
                border-bottom: none;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #121212;
                color: #e0e0e0;
            }
            """
        )

        self._build_ui()

        self._log_bridge = UiLogBridge()
        self._log_bridge.message.connect(self._append_log, Qt.ConnectionType.QueuedConnection)
        self._log_bridge.avionics_event.connect(
            self._on_avionics_log_event_ui,
            Qt.ConnectionType.QueuedConnection,
        )
        self._log_bridge.avionics_download_done.connect(
            self._on_avionics_download_done,
            Qt.ConnectionType.QueuedConnection,
        )
        self._log_bridge.avionics_download_failed.connect(
            self._on_avionics_download_failed,
            Qt.ConnectionType.QueuedConnection,
        )
        self._station.set_boot_logger(self._log_bridge.write)
        self._station.set_avionics_log_event_handler(self._log_bridge.emit_avionics_event)

        self._attitude.logging_toggled.connect(self._toggle_csv_logging)
        self._attitude.timestamp_record_toggled.connect(self._toggle_timestamp_record)
        self._attitude.avionics_log_start.connect(self._avionics_log_start)
        self._attitude.avionics_log_stop.connect(self._avionics_log_stop)
        self._attitude.avionics_log_download.connect(self._avionics_log_download)
        self._attitude.avionics_log_clear.connect(self._avionics_log_clear)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)

        self._startup_timer = QTimer(self)
        self._startup_timer.setSingleShot(True)
        self._startup_timer.timeout.connect(self._begin_startup)

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._log_periodic_status)

        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.timeout.connect(self._periodic_serial_recovery)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._startup_complete and not self._startup_timer.isActive():
            self._append_log("Initializing — waiting for window…")
            self._startup_timer.start(200)

    def _begin_startup(self) -> None:
        if self._startup_complete:
            return

        self._startup_attempts += 1
        mode = "Debug (USB)" if self._station.debug_mode else "Field (RFD900)"
        self._status_mode.setText(f"Mode: {mode}")

        if self._startup_attempts == 1:
            self._append_log(f"Mode: {mode}")
        self._append_log(
            f"Opening serial port… (attempt {self._startup_attempts}/{self._max_startup_attempts})"
        )

        try:
            if self._gui_settings.get("port") and self._gui_settings.get("baud"):
                self._station.init(
                    quiet=True,
                    port=str(self._gui_settings["port"]),
                    baud=int(self._gui_settings["baud"]),
                )
            else:
                self._station.init(quiet=True)
        except Exception as exc:
            self._serial_error = str(exc)
            self._append_log(f"Serial open failed: {exc}")
            if self._startup_attempts < self._max_startup_attempts:
                delay_ms = 1000 * self._startup_attempts
                self._append_log(f"Retrying in {delay_ms // 1000}s…")
                QTimer.singleShot(delay_ms, self._begin_startup)
                return
            self._append_log("Could not open serial port — will keep retrying in the background.")
        else:
            self._serial_error = None
            self._status_port.setText(f"Port: {self._station.port} @ {self._station.baud}")
            if self._log_path:
                try:
                    path = self._station.start_csv_logging(self._log_path)
                    self._append_log(f"Ground station CSV logging started: {path.name}")
                    self._sync_logging_ui()
                except OSError as exc:
                    self._append_log(f"Logging failed: {exc}")
            self._append_log("Port open — waiting for first telemetry…")
            QTimer.singleShot(500, self._query_avionics_storage)

        self._startup_complete = True
        self._timer.start(GUI_REFRESH_MS)
        self._status_timer.start(STATUS_LOG_INTERVAL_MS)
        self._reconnect_timer.start(SERIAL_RECONNECT_POLL_MS)
        self._refresh()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)

        self._tabs = QTabWidget()
        self._live_tab = QWidget()
        live_layout = QVBoxLayout(self._live_tab)
        live_layout.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        self._status_mode = QLabel("Mode: —")
        self._status_link = QLabel("Link: starting…")
        self._status_port = QLabel("Port: connecting…")
        self._status_seq = QLabel("Seq: —")
        for label in (self._status_mode, self._status_link, self._status_port, self._status_seq):
            label.setFont(QFont("Consolas", 10))
            header.addWidget(label)

        self._reconnect_btn = QPushButton("Reconnect")
        self._reconnect_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._reconnect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reconnect_btn.setMinimumHeight(32)
        self._reconnect_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #2a3a4a;
                color: #e0e0e0;
                border: 1px solid #445566;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover { background-color: #354a5a; }
            """
        )
        self._reconnect_btn.clicked.connect(self._manual_reconnect)
        header.addWidget(self._reconnect_btn)
        header.addStretch()
        live_layout.addLayout(header)

        main_split = QSplitter(Qt.Orientation.Vertical)
        main_split.setChildrenCollapsible(False)
        main_split.setHandleWidth(8)

        top_section = QWidget()
        top_layout = QVBoxLayout(top_section)
        top_layout.setContentsMargins(0, 0, 0, 0)

        top_split = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left.setMinimumWidth(340)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self._attitude = AttitudeDisplay()
        self._attitude.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left_layout.addWidget(self._attitude, stretch=1)
        top_split.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self._gps_panel = DataPanel(
            "GPS / Navigation",
            [
                ("fix", "Fix"),
                ("sats", "Satellites"),
                ("hdop", "HDOP"),
                ("lat", "Latitude"),
                ("lon", "Longitude"),
                ("alt", "Altitude MSL"),
                ("spd", "Ground speed"),
                ("crs", "Course"),
                ("climb", "Climb rate"),
                ("vn", "Velocity N"),
                ("ve", "Velocity E"),
                ("vd", "Velocity D"),
                ("utc", "UTC"),
                ("date", "Date"),
            ],
        )
        right_layout.addWidget(self._gps_panel, stretch=3)

        imu_row = QHBoxLayout()
        self._imu_att_panel = DataPanel(
            "IMU Attitude",
            [
                ("roll", "Roll"),
                ("pitch", "Pitch"),
                ("yaw", "Yaw"),
                ("temp", "Temperature"),
                ("frames", "Frames"),
                ("bytes", "Bytes"),
            ],
        )
        self._imu_sensor_panel = DataPanel(
            "IMU Sensors",
            [
                ("ax", "Accel X"),
                ("ay", "Accel Y"),
                ("az", "Accel Z"),
                ("gx", "Gyro X"),
                ("gy", "Gyro Y"),
                ("gz", "Gyro Z"),
                ("mx", "Mag X"),
                ("my", "Mag Y"),
                ("mz", "Mag Z"),
            ],
        )
        imu_row.addWidget(self._imu_att_panel)
        imu_row.addWidget(self._imu_sensor_panel)
        right_layout.addLayout(imu_row, stretch=2)

        top_split.addWidget(right)
        top_split.setStretchFactor(0, 4)
        top_split.setStretchFactor(1, 5)
        top_layout.addWidget(top_split)
        top_section.setMinimumHeight(280)
        main_split.addWidget(top_section)

        log_section = QWidget()
        log_layout = QVBoxLayout(log_section)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(0)

        log_header = _ConsoleHeader(main_split)
        log_header.setObjectName("logHeader")
        log_header.setFixedHeight(22)
        log_header.setCursor(Qt.CursorShape.SizeVerCursor)
        log_header_layout = QHBoxLayout(log_header)
        log_header_layout.setContentsMargins(10, 0, 10, 0)
        log_title = QLabel("Console")
        log_title.setFont(QFont("Segoe UI", 9))
        log_title.setStyleSheet("color: #777777; border: none;")
        log_hint = QLabel("drag to resize")
        log_hint.setFont(QFont("Segoe UI", 8))
        log_hint.setStyleSheet("color: #555555; border: none;")
        log_hint.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        log_header_layout.addWidget(log_title)
        log_header_layout.addStretch()
        log_header_layout.addWidget(log_hint)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(500)
        self._log.setMinimumHeight(72)

        log_layout.addWidget(log_header)
        log_layout.addWidget(self._log)
        log_section.setMinimumHeight(96)
        main_split.addWidget(log_section)

        main_split.setStretchFactor(0, 3)
        main_split.setStretchFactor(1, 1)
        main_split.setSizes([520, 160])

        live_layout.addWidget(main_split, stretch=1)

        self._analytics = FlightAnalyticsTab()
        self._settings_tab = self._create_settings_tab()
        self._tabs.addTab(self._live_tab, "Live")
        self._tabs.addTab(self._analytics, "Flight Analytics")
        self._tabs.addTab(self._settings_tab, "Setup")
        root.addWidget(self._tabs, stretch=1)

    def _append_log(self, message: str) -> None:
        self._log.appendPlainText(message)

    def _create_settings_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        title = QLabel("Serial Setup")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title.setStyleSheet("color: #e0e0e0;")
        layout.addWidget(title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFormAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)

        self._setup_port_combo = QComboBox()
        self._setup_port_combo.setEditable(True)
        self._setup_port_combo.setMinimumWidth(220)
        self._setup_baud_combo = QComboBox()
        self._setup_baud_combo.setMinimumWidth(140)
        self._setup_baud_combo.addItems([str(baud) for baud in DEFAULT_BAUD_RATES])

        form.addRow("COM Port:", self._setup_port_combo)
        form.addRow("Baud Rate:", self._setup_baud_combo)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._setup_apply_btn = QPushButton("Apply")
        self._setup_apply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._setup_apply_btn.setMinimumHeight(36)
        self._setup_apply_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._setup_apply_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #2a3a4a;
                color: #e0e0e0;
                border: 1px solid #445566;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover { background-color: #354a5a; }
            """
        )
        self._setup_apply_btn.clicked.connect(self._apply_serial_settings)
        btn_row.addWidget(self._setup_apply_btn)
        layout.addLayout(btn_row)

        info = QLabel(
            "Select the serial port and baud rate used by the avionics link. "
            "Changes are saved to settings.json and applied on next reconnect."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #aaaaaa;")
        layout.addWidget(info)

        layout.addStretch()
        self._refresh_serial_ports()
        return tab

    def _refresh_serial_ports(self) -> None:
        if self._setup_port_combo is None or self._setup_baud_combo is None:
            return

        current_port = self._setup_port_combo.currentText()
        self._setup_port_combo.clear()

        ports = list_ports.comports()
        for port in ports:
            self._setup_port_combo.addItem(port.device)

        if current_port:
            index = self._setup_port_combo.findText(current_port)
            if index >= 0:
                self._setup_port_combo.setCurrentIndex(index)
            else:
                self._setup_port_combo.setEditText(current_port)

        if not self._setup_port_combo.currentText():
            default_port = self._gui_settings.get("port") or self._station.port or ""
            if isinstance(default_port, str) and default_port:
                index = self._setup_port_combo.findText(default_port)
                if index >= 0:
                    self._setup_port_combo.setCurrentIndex(index)
                else:
                    self._setup_port_combo.setEditText(default_port)

        saved_baud = self._gui_settings.get("baud")
        if saved_baud is not None:
            index = self._setup_baud_combo.findText(str(saved_baud))
            if index >= 0:
                self._setup_baud_combo.setCurrentIndex(index)
            else:
                self._setup_baud_combo.addItem(str(saved_baud))
                self._setup_baud_combo.setCurrentText(str(saved_baud))

    def _apply_serial_settings(self) -> None:
        if self._setup_port_combo is None or self._setup_baud_combo is None:
            return

        port = self._setup_port_combo.currentText().strip()
        baud_text = self._setup_baud_combo.currentText().strip()
        if not port or not baud_text:
            self._append_log("Setup: port and baud must be supplied.")
            return

        try:
            baud = int(baud_text)
        except ValueError:
            self._append_log(f"Setup: invalid baud rate '{baud_text}'.")
            return

        self._gui_settings["port"] = port
        self._gui_settings["baud"] = baud
        save_gui_settings(port, baud)
        self._append_log(f"Saved serial settings: {port} @ {baud} baud.")

        try:
            self._station.set_serial_settings(port, baud)
        except Exception as exc:
            self._append_log(f"Setup: failed to apply settings locally: {exc}")
            return

        self._status_port.setText(f"Port: {self._station.port} @ {self._station.baud}")

    def _manual_reconnect(self) -> None:
        if not self._startup_complete:
            self._append_log("Reconnect: serial not ready yet.")
            return

        self._append_log("Manual reconnect requested…")
        try:
            self._station.reconnect_serial()
            self._serial_error = None
            self._stale_since = None
            self._status_port.setText(f"Port: {self._station.port} @ {self._station.baud}")
            self._append_log("Serial port reopened — waiting for telemetry…")
        except Exception as exc:
            self._append_log(f"Manual reconnect failed: {exc}")

    def _toggle_csv_logging(self) -> None:
        if self._station.is_csv_logging():
            path = self._station.stop_csv_logging()
            if path is not None:
                self._append_log(f"Ground station CSV logging stopped: {path.name}")
                self._analytics.notify_log_saved(path)
            self._attitude.set_logging_state(False)
            if self._timestamp_record_active:
                self._end_timestamp_session("Ground-station log stopped", stopped="gs")
            return

        try:
            path = self._station.start_csv_logging()
        except OSError as exc:
            self._append_log(f"Logging failed: {exc}")
            self._attitude.set_logging_state(False)
            return

        self._append_log(f"Ground station CSV logging started: {path.name}")
        self._attitude.set_logging_state(True, str(path))
        self._analytics.refresh_file_list()

    def _clear_timestamp_record_state(self, detail: str = "") -> None:
        self._timestamp_record_active = False
        self._attitude.set_timestamp_record_state(False, detail)

    def _end_timestamp_session(self, reason: str, *, stopped: str) -> None:
        """Stop the other logger when one side of a timestamp session ends."""
        if stopped != "avionics" and self._avionics_recording:
            try:
                self._station.avionics_log_stop()
            except Exception as exc:
                self._append_log(f"Timestamp record: avionics stop failed: {exc}")
            self._avionics_recording = False
            self._release_avionics_log_controls("Ready to download")

        if stopped != "gs" and self._station.is_csv_logging():
            path = self._station.stop_csv_logging()
            if path is not None:
                self._analytics.notify_log_saved(path)
            self._attitude.set_logging_state(False)

        self._clear_timestamp_record_state(reason)
        self._append_log(f"Timestamp record ended: {reason}")

    def _toggle_timestamp_record(self) -> None:
        if not self._startup_complete:
            self._append_log("Timestamp record: serial not ready")
            return

        if self._timestamp_record_active:
            self._stop_timestamp_record()
            return

        self._start_timestamp_record()

    def _start_timestamp_record(self) -> None:
        if self._station.is_csv_logging() or self._avionics_recording:
            self._append_log("Timestamp record: stop existing logs before starting a new session")
            return

        self._ensure_avionics_log_unlocked()

        latest = self._station.telemetry.get_latest()
        sync_uptime_ms = latest.uptime_ms if latest is not None else None

        self._timestamp_record_active = True
        self._avionics_recording = True
        self._attitude.set_timestamp_record_state(True, "Starting both logs…")
        self._attitude.set_avionics_log_state("recording", "Starting…")
        self._attitude.set_logging_state(True, "Starting…")

        avionics_ok = False
        gs_ok = False
        gs_path = None

        try:
            self._station.avionics_log_start()
            avionics_ok = True
        except Exception as exc:
            self._append_log(f"Timestamp record: avionics start failed: {exc}")

        try:
            gs_path = self._station.start_csv_logging()
            gs_ok = True
            self._attitude.set_logging_state(True, str(gs_path))
            self._analytics.refresh_file_list()
        except OSError as exc:
            self._append_log(f"Timestamp record: ground-station start failed: {exc}")
            self._attitude.set_logging_state(False)

        if avionics_ok and gs_ok and gs_path is not None:
            detail = f"Recording — GS {gs_path.name}"
            if sync_uptime_ms is not None:
                detail += f" · uptime {sync_uptime_ms} ms"
            self._attitude.set_timestamp_record_state(True, detail)
            self._append_log(
                "Timestamp record started: avionics remote record + "
                f"{gs_path.name}"
                + (f" (uptime {sync_uptime_ms} ms)" if sync_uptime_ms is not None else "")
            )
            return

        if gs_ok:
            path = self._station.stop_csv_logging()
            if path is not None:
                self._append_log(f"Timestamp record rollback: stopped {path.name}")
            self._attitude.set_logging_state(False)

        if avionics_ok:
            try:
                self._station.avionics_log_stop()
            except Exception:
                pass

        self._avionics_recording = False
        self._release_avionics_log_controls("Start failed — ready to retry")
        self._clear_timestamp_record_state("Start failed")

    def _stop_timestamp_record(self) -> None:
        if not self._timestamp_record_active:
            return

        stopped: list[str] = []
        if self._avionics_recording:
            try:
                self._station.avionics_log_stop()
                self._attitude.set_avionics_log_state("recording", "Stopping…")
                stopped.append("avionics")
            except Exception as exc:
                self._append_log(f"Timestamp record: avionics stop failed: {exc}")

        if self._station.is_csv_logging():
            path = self._station.stop_csv_logging()
            if path is not None:
                stopped.append(f"GS ({path.name})")
                self._analytics.notify_log_saved(path)
            self._attitude.set_logging_state(False)

        self._avionics_recording = False
        self._clear_timestamp_record_state(
            "Stopped" if stopped else "Start avionics + ground-station logs together"
        )
        if stopped:
            self._append_log(f"Timestamp record stopped: {', '.join(stopped)}")

    def _sync_logging_ui(self) -> None:
        if self._station.is_csv_logging():
            path = self._station.csv_log_path
            self._attitude.set_logging_state(True, str(path) if path else "")
        else:
            self._attitude.set_logging_state(False)

    def _query_avionics_storage(self) -> None:
        if self._serial_error or not self._startup_complete:
            return
        try:
            self._station.query_avionics_storage()
        except Exception as exc:
            self._append_log(f"Onboard storage query failed: {exc}")

    def _on_avionics_log_event_ui(self, line: str) -> None:
        if "Start recording trigger received" in line or line.startswith("Blivit,LOG,OK,START"):
            self._avionics_recording = True
            self._attitude.set_avionics_log_state("recording")
        elif "Stop recording trigger received" in line:
            self._avionics_recording = False
            if self._timestamp_record_active:
                self._end_timestamp_session("Avionics log stopped", stopped="avionics")
            nbytes = self._station.onboard_log_bytes
            if nbytes and nbytes > 0:
                kb = nbytes / 1024.0
                self._release_avionics_log_controls(f"Ready to download ({kb:.1f} KB on device)")
            else:
                self._release_avionics_log_controls("Ready to download")
        elif line.startswith("Blivit,LOG,OK,STOP,"):
            self._avionics_recording = False
            if self._timestamp_record_active:
                self._end_timestamp_session("Avionics log stopped", stopped="avionics")
            nbytes = self._station.onboard_log_bytes
            if nbytes and nbytes > 0:
                kb = nbytes / 1024.0
                rows = self._station.onboard_log_rows
                detail = f"Ready to download ({kb:.1f} KB"
                if rows > 0:
                    detail += f", {rows} rows"
                detail += " on device)"
                self._release_avionics_log_controls(detail)
            else:
                self._release_avionics_log_controls("Ready to download")
        elif line.startswith("Blivit,LOG,ERR,"):
            self._avionics_recording = False
            if self._timestamp_record_active:
                self._clear_timestamp_record_state("Avionics command failed")
            self._release_avionics_log_controls("Command failed — ready to retry")
        elif "Download accepted" in line:
            if self._avionics_download_ui_active:
                self._attitude.set_avionics_log_state("downloading", "Receiving…")
        elif line.startswith("Blivit,LOG,OK,ABORT"):
            self._release_avionics_log_controls("Download cancelled — ready to retry")
        elif line.startswith("Blivit,LOG,END,"):
            if self._avionics_download_ui_active:
                nbytes = self._station.onboard_log_bytes
                if nbytes and nbytes > 0:
                    kb = nbytes / 1024.0
                    self._release_avionics_log_controls(f"Download complete ({kb:.1f} KB saved)")
                else:
                    self._release_avionics_log_controls("Download complete")
            else:
                self._release_avionics_log_controls("Ready to download")
        elif "Onboard flight data cleared" in line:
            self._release_avionics_log_controls("Flash log cleared")

    def _release_avionics_log_controls(self, detail: str = "Idle") -> None:
        """Re-enable avionics log buttons after download completes, fails, or is cancelled."""
        self._avionics_download_ui_active = False
        self._attitude.set_avionics_log_state("idle", detail)

    def _ensure_avionics_log_unlocked(self) -> None:
        """Recover from a stuck download state so Record / Download / Clear work again."""
        if self._avionics_download_ui_active or self._station.is_avionics_downloading():
            self._station.cancel_avionics_download()
            self._release_avionics_log_controls("Recovered — ready to retry")

    def _avionics_log_clear(self) -> None:
        if not self._startup_complete:
            self._append_log("Avionics log: serial not ready")
            return
        self._ensure_avionics_log_unlocked()
        try:
            self._station.avionics_log_clear()
            self._append_log("Sending clear flight data command…")
        except Exception as exc:
            self._append_log(f"Clear flight data failed: {exc}")
            self._release_avionics_log_controls("Clear failed — ready to retry")

    def _avionics_log_start(self) -> None:
        if not self._startup_complete:
            self._append_log("Avionics log: serial not ready")
            return
        self._ensure_avionics_log_unlocked()
        try:
            self._attitude.set_avionics_log_state("recording", "Starting…")
            self._avionics_recording = True
            self._station.avionics_log_start()
            self._append_log("Sending remote record command…")
        except Exception as exc:
            self._avionics_recording = False
            self._append_log(f"Avionics log start failed: {exc}")
            self._release_avionics_log_controls("Start failed — ready to retry")

    def _avionics_log_stop(self) -> None:
        if not self._startup_complete:
            return
        self._ensure_avionics_log_unlocked()
        try:
            self._attitude.set_avionics_log_state("recording", "Stopping…")
            self._station.avionics_log_stop()
            self._append_log("Sending stop recording command…")
        except Exception as exc:
            self._append_log(f"Avionics log stop failed: {exc}")
            self._release_avionics_log_controls("Stop failed — ready to retry")
            return
        self._avionics_recording = False
        if self._timestamp_record_active:
            self._end_timestamp_session("Avionics stop sent", stopped="avionics")
            return

    def _avionics_log_download(self) -> None:
        if not self._startup_complete:
            self._append_log("Avionics log: serial not ready")
            return
        if self._avionics_download_ui_active:
            self._append_log("Avionics log download already in progress")
            return

        self._ensure_avionics_log_unlocked()
        self._avionics_download_ui_active = True
        self._attitude.set_avionics_log_state("downloading")
        self._append_log("Requesting ESP32 log download…")

        def work() -> None:
            try:
                path = self._station.download_avionics_log()
            except Exception as exc:
                self._log_bridge.emit_download_failed(str(exc))
                return
            self._log_bridge.emit_download_done(str(path))

        threading.Thread(target=work, name="avionics-log-download", daemon=True).start()

    def _on_avionics_download_done(self, path: str) -> None:
        from pathlib import Path

        saved = Path(path)
        self._release_avionics_log_controls(saved.name)
        self._append_log(f"Saved ESP32 log: {saved}")
        self._analytics.refresh_file_list()
        self._analytics.notify_log_saved(saved)

    def _on_avionics_download_failed(self, message: str) -> None:
        self._station.cancel_avionics_download()
        short = message if len(message) <= 120 else message[:117] + "…"
        self._release_avionics_log_controls(f"Download failed — {short}")
        self._append_log(f"ESP32 log download failed: {message}")

    def _refresh(self) -> None:
        if not self._startup_complete:
            return
        try:
            self._refresh_inner()
        except Exception as exc:
            self._append_log(f"[GUI] refresh error: {exc}")

    def _refresh_inner(self) -> None:
        latest, seq = self._station.telemetry.read_latest()
        self._update_comms(latest)

        if latest is None:
            return

        if not self._first_telemetry_logged:
            self._first_telemetry_logged = True
            self._append_log(f"First telemetry received (seq {latest.sequence})")

        if seq == self._last_seq:
            return

        self._last_seq = seq
        self._update_status(latest)
        self._update_gps(latest)
        self._update_imu(latest)

    def _link_state_from_telemetry(self, latest: Optional[TelemetrySnapshot]) -> str:
        stale_ms = self._station.telemetry_stale_ms
        if self._station.is_avionics_downloading() and self._station.is_serial_link_alive(
            stale_ms
        ):
            return "live"
        if latest is None:
            return "waiting"
        age_ms = (time.monotonic() - latest.received_at) * 1000.0
        if age_ms > stale_ms:
            return "stale"
        return "live"

    def _update_comms(self, latest: Optional[TelemetrySnapshot]) -> None:
        mode = "Debug (USB serial)" if self._station.debug_mode else "Field (RFD900)"
        port = self._station.port or "—"
        baud = self._station.baud or 0
        downloading = self._station.is_avionics_downloading()
        stale_ms = self._station.telemetry_stale_ms
        serial_age_ms = self._station.serial_age_ms()
        serial_alive = self._station.is_serial_link_alive(stale_ms)

        if self._serial_error and not self._station.reader_alive:
            link_state = "error"
            error = self._serial_error
            sequence = None
            uptime_ms = None
            age_ms = None
            source = None
        elif downloading and serial_alive:
            link_state = "live"
            error = None
            snap = latest
            sequence = snap.sequence if snap is not None else None
            uptime_ms = snap.uptime_ms if snap is not None else None
            source = snap.source if snap is not None else "download"
            age_ms = serial_age_ms
        elif latest is None:
            link_state = "waiting" if (serial_alive or not downloading) else "stale"
            error = None
            sequence = None
            uptime_ms = None
            age_ms = serial_age_ms
            source = None
        else:
            error = None
            snap = latest
            age_ms = (time.monotonic() - snap.received_at) * 1000.0
            if downloading and serial_alive:
                link_state = "live"
                age_ms = min(age_ms, serial_age_ms or age_ms)
            else:
                link_state = "stale" if age_ms > stale_ms else "live"
            sequence = snap.sequence
            uptime_ms = snap.uptime_ms
            source = snap.source

        self._attitude.update_comms(
            port=port,
            baud=baud,
            mode=mode,
            link_state=link_state,
            sequence=sequence,
            uptime_ms=uptime_ms,
            age_ms=age_ms,
            source=source,
            error=error,
        )
        self._station.update_link_state(link_state)

        if self._serial_error:
            self._status_link.setText("Link: error")
            self._status_link.setStyleSheet("color: #ff4444;")
        elif link_state == "live" and downloading:
            self._status_link.setText("Link: live (downloading)")
            self._status_link.setStyleSheet("color: #44dd66;")
        elif latest is None and not serial_alive:
            self._status_link.setText("Link: waiting…")
            self._status_link.setStyleSheet("color: #ffaa00;")
        elif link_state == "stale":
            self._status_link.setText("Link: stale")
            self._status_link.setStyleSheet("color: #ff8844;")
        else:
            self._status_link.setText("Link: live")
            self._status_link.setStyleSheet("color: #44dd66;")

        self._maybe_recover_serial(link_state)

    def _periodic_serial_recovery(self) -> None:
        """Background poll — keeps trying to reopen serial after USB drop or stale link."""
        if not self._startup_complete or self._station.is_avionics_downloading():
            return

        # Debug USB: only reopen on hard serial failure. Bursty OS buffering can
        # look like a stale link; reconnecting clears the RX buffer and worsens jitter.
        if self._station.debug_mode:
            if (
                self._station.reader_alive
                and self._station.serial_is_open
                and not self._station.serial_fault
            ):
                self._stale_since = None
                return
            reason = "serial read error" if self._station.serial_fault else "serial reader stopped"
            if not self._station.serial_is_open:
                reason = "serial port closed"
            self._attempt_serial_reconnect(reason)
            return

        latest, _seq = self._station.telemetry.read_latest()
        link_state = self._link_state_from_telemetry(latest)

        if (
            link_state == "live"
            and self._station.reader_alive
            and not self._station.serial_fault
            and self._station.serial_is_open
        ):
            self._stale_since = None
            return

        reason = "no fresh telemetry"
        if self._station.serial_fault:
            reason = f"serial read error: {self._station.serial_fault}"
        elif not self._station.reader_alive:
            reason = "serial reader stopped"
        elif not self._station.serial_is_open:
            reason = "serial port closed"

        if link_state == "stale":
            if self._stale_since is None:
                self._stale_since = time.monotonic()
            elif (time.monotonic() - self._stale_since) * 1000.0 < SERIAL_STALE_RECONNECT_MS:
                return
        elif link_state == "waiting" and latest is not None:
            # Had telemetry before, now waiting — treat like stale
            if self._stale_since is None:
                self._stale_since = time.monotonic()
            elif (time.monotonic() - self._stale_since) * 1000.0 < SERIAL_STALE_RECONNECT_MS:
                return
        elif link_state == "waiting" and latest is None:
            # Never connected — still retry open periodically
            pass

        self._attempt_serial_reconnect(reason)

    def _maybe_recover_serial(self, link_state: str) -> None:
        if not self._startup_complete:
            return
        if self._station.is_avionics_downloading():
            self._stale_since = None
            return

        if link_state == "live":
            self._stale_since = None

    def _attempt_serial_reconnect(self, reason: str) -> None:
        now = time.monotonic()
        if (now - self._last_reconnect_attempt) < SERIAL_RECONNECT_COOLDOWN_S:
            return

        self._last_reconnect_attempt = now
        self._append_log(f"Reopening serial port ({reason})…")
        try:
            self._station.reconnect_serial()
            self._serial_error = None
            self._stale_since = None
            self._status_port.setText(f"Port: {self._station.port} @ {self._station.baud}")
            self._append_log("Serial port reopened — waiting for telemetry…")
        except Exception as exc:
            self._append_log(f"Serial reconnect failed: {exc}")
            self._stale_since = time.monotonic()

    def _log_periodic_status(self) -> None:
        if not self._startup_complete:
            return
        if self._station.is_avionics_downloading():
            return
        if not self._station.reader_alive and not self._station.serial_is_open:
            return

        line = self._station.format_link_status()
        self._append_log(line)

    def _update_status(self, snap: TelemetrySnapshot) -> None:
        self._status_link.setText("Link: live")
        self._status_link.setStyleSheet("color: #44dd66;")
        self._status_seq.setText(f"Seq: {snap.sequence}  Uptime: {snap.uptime_ms / 1000:.1f}s")

    def _update_gps(self, snap: TelemetrySnapshot) -> None:
        fix_color = "#44dd66" if snap.gps_valid else "#ff6666"
        self._gps_panel.set_value("fix", "3D FIX" if snap.gps_valid else "NO FIX", color=fix_color)
        self._gps_panel.set_value("sats", str(snap.gps_satellites))
        self._gps_panel.set_value("hdop", f"{snap.hdop:.1f}")
        self._gps_panel.set_value("lat", f"{snap.latitude:.6f}°")
        self._gps_panel.set_value("lon", f"{snap.longitude:.6f}°")
        self._gps_panel.set_value("alt", f"{snap.altitude:.1f} m")
        self._gps_panel.set_value("spd", f"{snap.speed:.2f} m/s")
        self._gps_panel.set_value("crs", f"{snap.course:.1f}°")
        self._gps_panel.set_value("climb", f"{snap.climb_rate:+.2f} m/s")
        self._gps_panel.set_value("vn", f"{snap.vel_n:+.2f} m/s")
        self._gps_panel.set_value("ve", f"{snap.vel_e:+.2f} m/s")
        self._gps_panel.set_value("vd", f"{snap.vel_d:+.2f} m/s")
        self._gps_panel.set_value("utc", snap.utc or "—")
        self._gps_panel.set_value("date", snap.date or "—")

    def _update_imu(self, snap: TelemetrySnapshot) -> None:
        self._attitude.set_attitude(snap.roll, snap.pitch, snap.yaw)
        self._imu_att_panel.set_value("roll", f"{snap.roll:+.2f}°")
        self._imu_att_panel.set_value("pitch", f"{snap.pitch:+.2f}°")
        self._imu_att_panel.set_value("yaw", f"{snap.yaw:+.2f}°")
        self._imu_att_panel.set_value("temp", f"{snap.temperature:.2f} °C")
        self._imu_att_panel.set_value("frames", str(snap.imu_frames))
        self._imu_att_panel.set_value("bytes", str(snap.imu_bytes))
        self._imu_sensor_panel.set_value("ax", f"{snap.accel_x:.3f} m/s²")
        self._imu_sensor_panel.set_value("ay", f"{snap.accel_y:.3f} m/s²")
        self._imu_sensor_panel.set_value("az", f"{snap.accel_z:.3f} m/s²")
        self._imu_sensor_panel.set_value("gx", f"{snap.gyro_x:.2f} °/s")
        self._imu_sensor_panel.set_value("gy", f"{snap.gyro_y:.2f} °/s")
        self._imu_sensor_panel.set_value("gz", f"{snap.gyro_z:.2f} °/s")
        self._imu_sensor_panel.set_value("mx", f"{snap.mag_x:.1f}")
        self._imu_sensor_panel.set_value("my", f"{snap.mag_y:.1f}")
        self._imu_sensor_panel.set_value("mz", f"{snap.mag_z:.1f}")

    def closeEvent(self, event) -> None:
        if self._station.is_csv_logging():
            path = self._station.stop_csv_logging()
            if path is not None:
                self._append_log(f"Ground station CSV logging stopped: {path.name}")
        self._station.close()
        super().closeEvent(event)


def _install_exception_hook() -> None:
    def _hook(exc_type, exc_value, exc_tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        sys.stderr.write(text)
        app = QApplication.instance()
        if app is not None:
            for widget in app.topLevelWidgets():
                if isinstance(widget, GroundStationWindow):
                    widget._append_log(f"[GUI] fatal error:\n{text.rstrip()}")
                    break
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook


def run_gui(
    station: GroundStation,
    *,
    log_path: Optional[str] = None,
) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Blivit Ground Station")
    _install_exception_hook()

    window = GroundStationWindow(station, log_path=log_path)
    window.show()
    return app.exec()
