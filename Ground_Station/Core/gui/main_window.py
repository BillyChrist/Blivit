"""Main avionics-style ground station window."""

from __future__ import annotations

import sys
import time
import traceback
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from gui.attitude_indicator import AttitudeDisplay
from gui.log_bridge import UiLogBridge
from config import GUI_REFRESH_MS, TELEMETRY_STALE_MS
from ground_station import GroundStation
from telemetry import TelemetrySnapshot


class DataPanel(QGroupBox):
    def __init__(self, title: str, rows: list[tuple[str, str]], parent=None) -> None:
        super().__init__(title, parent)
        self._labels: dict[str, QLabel] = {}
        layout = QGridLayout(self)
        layout.setColumnStretch(1, 1)
        font_value = QFont("Consolas", 11)

        for row, (key, label_text) in enumerate(rows):
            name = QLabel(label_text)
            name.setStyleSheet("color: #999999;")
            value = QLabel("—")
            value.setFont(font_value)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            value.setStyleSheet("color: #e8e8e8;")
            layout.addWidget(name, row, 0)
            layout.addWidget(value, row, 1)
            self._labels[key] = value

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
            """
        )

        self._build_ui()

        self._log_bridge = UiLogBridge()
        self._log_bridge.message.connect(self._append_log, Qt.ConnectionType.QueuedConnection)
        self._station.set_boot_logger(self._log_bridge.write)

        self._attitude.logging_toggled.connect(self._toggle_csv_logging)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)

        self._startup_timer = QTimer(self)
        self._startup_timer.setSingleShot(True)
        self._startup_timer.timeout.connect(self._begin_startup)

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
            self._station.init(quiet=True)
        except Exception as exc:
            self._serial_error = str(exc)
            self._append_log(f"Serial open failed: {exc}")
            if self._startup_attempts < self._max_startup_attempts:
                delay_ms = 1000 * self._startup_attempts
                self._append_log(f"Retrying in {delay_ms // 1000}s…")
                QTimer.singleShot(delay_ms, self._begin_startup)
                return
            self._append_log("Close PlatformIO serial monitor, then restart the GUI.")
        else:
            self._serial_error = None
            self._status_port.setText(f"Port: {self._station.port} @ {self._station.baud}")
            if self._log_path:
                try:
                    path = self._station.start_csv_logging(self._log_path)
                    self._append_log(f"Logging started: {path}")
                    self._sync_logging_ui()
                except OSError as exc:
                    self._append_log(f"Logging failed: {exc}")
            self._append_log("Port open — waiting for first telemetry…")

        self._startup_complete = True
        self._timer.start(GUI_REFRESH_MS)
        self._refresh()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        header = QHBoxLayout()
        self._status_mode = QLabel("Mode: —")
        self._status_link = QLabel("Link: starting…")
        self._status_port = QLabel("Port: connecting…")
        self._status_seq = QLabel("Seq: —")
        for label in (self._status_mode, self._status_link, self._status_port, self._status_seq):
            label.setFont(QFont("Consolas", 10))
            header.addWidget(label)
        header.addStretch()
        root.addLayout(header)

        top_split = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._attitude = AttitudeDisplay()
        left_layout.addStretch()
        left_layout.addWidget(self._attitude, alignment=Qt.AlignmentFlag.AlignCenter)
        left_layout.addStretch()
        top_split.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)

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
        right_layout.addWidget(self._gps_panel)

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
        right_layout.addLayout(imu_row)

        top_split.addWidget(right)
        top_split.setStretchFactor(0, 2)
        top_split.setStretchFactor(1, 3)
        root.addWidget(top_split, stretch=3)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(500)
        root.addWidget(self._log, stretch=1)

    def _append_log(self, message: str) -> None:
        self._log.appendPlainText(message)

    def _toggle_csv_logging(self) -> None:
        if self._station.is_csv_logging():
            path = self._station.stop_csv_logging()
            if path is not None:
                self._append_log(f"Logging stopped: {path}")
            self._attitude.set_logging_state(False)
            return

        try:
            path = self._station.start_csv_logging()
        except OSError as exc:
            self._append_log(f"Logging failed: {exc}")
            self._attitude.set_logging_state(False)
            return

        self._append_log(f"Logging started: {path}")
        self._attitude.set_logging_state(True, str(path))

    def _sync_logging_ui(self) -> None:
        if self._station.is_csv_logging():
            path = self._station.csv_log_path
            self._attitude.set_logging_state(True, str(path) if path else "")
        else:
            self._attitude.set_logging_state(False)

    def _refresh(self) -> None:
        if not self._startup_complete:
            return
        try:
            self._refresh_inner()
        except Exception as exc:
            self._append_log(f"[GUI] refresh error: {exc}")

    def _refresh_inner(self) -> None:
        state = self._station.telemetry.copy_state()
        self._update_comms(state)

        if state.latest is None:
            return

        if not self._first_telemetry_logged:
            self._first_telemetry_logged = True
            self._append_log(f"First telemetry received (seq {state.latest.sequence})")

        if state.seq == self._last_seq:
            return

        self._last_seq = state.seq
        snap = state.latest
        self._update_status(snap)
        self._update_gps(snap)
        self._update_imu(snap)

    def _update_comms(self, state) -> None:
        mode = "Debug (USB serial)" if self._station.debug_mode else "Field (RFD900)"
        port = self._station.port or "—"
        baud = self._station.baud or 0

        if self._serial_error:
            link_state = "error"
            error = self._serial_error
            sequence = None
            uptime_ms = None
            age_ms = None
            source = None
        elif state.latest is None:
            link_state = "waiting"
            error = None
            sequence = None
            uptime_ms = None
            age_ms = None
            source = None
        else:
            error = None
            snap = state.latest
            age_ms = (time.monotonic() - snap.received_at) * 1000.0
            sequence = snap.sequence
            uptime_ms = snap.uptime_ms
            source = snap.source
            if age_ms > TELEMETRY_STALE_MS:
                link_state = "stale"
            else:
                link_state = "live"

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

        if self._serial_error:
            self._status_link.setText("Link: error")
            self._status_link.setStyleSheet("color: #ff4444;")
        elif state.latest is None:
            self._status_link.setText("Link: waiting…")
            self._status_link.setStyleSheet("color: #ffaa00;")
        elif link_state == "stale":
            self._status_link.setText("Link: stale")
            self._status_link.setStyleSheet("color: #ff8844;")
        else:
            self._status_link.setText("Link: live")
            self._status_link.setStyleSheet("color: #44dd66;")

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
                self._append_log(f"Logging stopped: {path}")
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
