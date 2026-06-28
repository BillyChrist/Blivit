"""Flight Analytics tab — plot telemetry CSV logs."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 — registers 3D projection
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from telemetry_csv import TelemetryLog, discover_telemetry_logs, load_telemetry_csv

_PLOTS: dict[str, Callable[[Figure, TelemetryLog], None]] = {}


def _register_plot(title: str):
    def decorator(func: Callable[[Figure, TelemetryLog], None]):
        _PLOTS[title] = func
        return func

    return decorator


@_register_plot("Attitude — roll / pitch / yaw vs time")
def _plot_attitude(fig: Figure, log: TelemetryLog) -> None:
    ax = fig.add_subplot(111)
    ax.plot(log.t_sec, log.roll, label="Roll", color="#5dade2", linewidth=1.2)
    ax.plot(log.t_sec, log.pitch, label="Pitch", color="#58d68d", linewidth=1.2)
    ax.plot(log.t_sec, log.yaw, label="Yaw", color="#f5b041", linewidth=1.2)
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Angle [deg]")
    ax.set_title("Attitude vs time")
    ax.grid(True, alpha=0.35)
    ax.legend(loc="upper right")


@_register_plot("Ground track — northing vs easting")
def _plot_ground_track(fig: Figure, log: TelemetryLog) -> None:
    east, north, _ = log.local_enu_m()
    ax = fig.add_subplot(111)
    if east.size == 0:
        ax.text(0.5, 0.5, "No valid GPS fixes", ha="center", va="center", transform=ax.transAxes)
        return

    ax.plot(east, north, color="#5dade2", linewidth=1.5)
    ax.scatter(east[0], north[0], color="#58d68d", s=40, label="Start", zorder=5)
    ax.scatter(east[-1], north[-1], color="#ec7063", s=40, label="End", zorder=5)
    ax.set_xlabel("Easting [m]")
    ax.set_ylabel("Northing [m]")
    ax.set_title("Ground track (local tangent plane, +E / +N)")
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True, alpha=0.35)
    ax.legend(loc="best")


@_register_plot("3D flight path — east / north / altitude MSL")
def _plot_3d_path(fig: Figure, log: TelemetryLog) -> None:
    east, north, alt_msl = log.gps_track_enu_msl()
    ax = fig.add_subplot(111, projection="3d")
    if east.size == 0:
        ax.text2D(0.5, 0.5, "No valid GPS fixes", transform=ax.transAxes, ha="center")
        return

    ax.plot(east, north, alt_msl, color="#5dade2", linewidth=1.5)
    ax.scatter(east[0], north[0], alt_msl[0], color="#58d68d", s=30, label="Start")
    ax.scatter(east[-1], north[-1], alt_msl[-1], color="#ec7063", s=30, label="End")
    ax.set_xlabel("Easting [m]")
    ax.set_ylabel("Northing [m]")
    ax.set_zlabel("Altitude MSL [m]")
    ax.set_title("3D flight path (local E / N, altitude MSL)")
    ax.legend(loc="upper right")


@_register_plot("Acceleration vs time")
def _plot_acceleration(fig: Figure, log: TelemetryLog) -> None:
    ax = fig.add_subplot(111)
    ax.plot(log.t_sec, log.accel_x, label="Ax", color="#e74c3c", linewidth=1.0, alpha=0.85)
    ax.plot(log.t_sec, log.accel_y, label="Ay", color="#58d68d", linewidth=1.0, alpha=0.85)
    ax.plot(log.t_sec, log.accel_z, label="Az", color="#5dade2", linewidth=1.0, alpha=0.85)
    ax.plot(log.t_sec, log.accel_mag, label="|A|", color="#f5b041", linewidth=1.4)
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Acceleration [m/s²]")
    ax.set_title("Acceleration vs time")
    ax.grid(True, alpha=0.35)
    ax.legend(loc="upper right", ncol=2)


@_register_plot("Velocity vs time")
def _plot_velocity(fig: Figure, log: TelemetryLog) -> None:
    ax = fig.add_subplot(111)
    ax.plot(log.t_sec, log.speed, label="Ground speed", color="#f5b041", linewidth=1.4)
    ax.plot(log.t_sec, log.vel_horiz, label="|V horizontal|", color="#bb8fce", linewidth=1.0, alpha=0.9)
    ax.plot(log.t_sec, log.vel_n, label="V north", color="#58d68d", linewidth=1.0, alpha=0.85)
    ax.plot(log.t_sec, log.vel_e, label="V east", color="#5dade2", linewidth=1.0, alpha=0.85)
    ax.plot(log.t_sec, -log.vel_d, label="Climb (+up)", color="#ec7063", linewidth=1.0, alpha=0.85)
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Velocity [m/s]")
    ax.set_title("Velocity vs time")
    ax.grid(True, alpha=0.35)
    ax.legend(loc="upper right", fontsize=8)


class FlightAnalyticsTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._log: Optional[TelemetryLog] = None
        self._build_ui()
        self.refresh_file_list()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        top_panel = QFrame()
        top_panel.setStyleSheet(
            """
            QFrame {
                background-color: #1a1a1a;
                border: 1px solid #333333;
                border-radius: 4px;
            }
            """
        )
        top_layout = QVBoxLayout(top_panel)
        top_layout.setContentsMargins(10, 10, 10, 10)
        top_layout.setSpacing(8)

        plot_row = QHBoxLayout()
        plot_label = QLabel("Plot type")
        plot_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._plot_combo = QComboBox()
        self._plot_combo.addItems(list(_PLOTS.keys()))
        self._plot_combo.currentTextChanged.connect(self._render_plot)
        plot_row.addWidget(plot_label)
        plot_row.addWidget(self._plot_combo, stretch=1)
        top_layout.addLayout(plot_row)

        logs_label = QLabel("Telemetry logs")
        logs_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        top_layout.addWidget(logs_label)

        self._file_list = QListWidget()
        self._file_list.setMaximumHeight(120)
        self._file_list.currentItemChanged.connect(self._on_file_selected)
        top_layout.addWidget(self._file_list)

        btn_row = QHBoxLayout()
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self.refresh_file_list)
        self._browse_btn = QPushButton("Browse…")
        self._browse_btn.clicked.connect(self._browse_file)
        btn_row.addWidget(self._refresh_btn)
        btn_row.addWidget(self._browse_btn)
        btn_row.addStretch()
        top_layout.addLayout(btn_row)

        self._meta = QLabel("Select a log file")
        self._meta.setWordWrap(True)
        self._meta.setStyleSheet("color: #888888;")
        top_layout.addWidget(self._meta)

        root.addWidget(top_panel)

        self._figure = Figure(figsize=(8, 5), dpi=100)
        self._figure.set_facecolor("#121212")
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._toolbar = NavigationToolbar2QT(self._canvas)
        self._toolbar.setStyleSheet("background-color: #1a1a1a; color: #cccccc;")

        root.addWidget(self._toolbar)
        root.addWidget(self._canvas, stretch=1)

        self._show_placeholder("Load a telemetry CSV from received_data/")

    def refresh_file_list(self) -> None:
        current = self._file_list.currentItem()
        current_path = current.data(Qt.ItemDataRole.UserRole) if current else None

        self._file_list.clear()
        for path in discover_telemetry_logs():
            item = QListWidgetItem(path.name)
            item.setToolTip(str(path))
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self._file_list.addItem(item)
            if current_path and str(path) == current_path:
                self._file_list.setCurrentItem(item)

        if self._file_list.count() and self._file_list.currentItem() is None:
            self._file_list.setCurrentRow(0)

        if self._file_list.count() == 0:
            self._meta.setText("No telemetry_*.csv files found")
            self._show_placeholder("No logs in received_data/")

    def notify_log_saved(self, path: str | Path) -> None:
        self.refresh_file_list()
        target = str(Path(path).resolve())
        for row in range(self._file_list.count()):
            item = self._file_list.item(row)
            if item and item.data(Qt.ItemDataRole.UserRole) == target:
                self._file_list.setCurrentItem(item)
                break

    def _browse_file(self) -> None:
        existing = discover_telemetry_logs()
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open telemetry CSV",
            str(existing[0].parent) if existing else "",
            "CSV files (*.csv)",
        )
        if not path:
            return

        item = QListWidgetItem(Path(path).name)
        item.setToolTip(path)
        item.setData(Qt.ItemDataRole.UserRole, path)
        self._file_list.insertItem(0, item)
        self._file_list.setCurrentItem(item)

    def _on_file_selected(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        path = current.data(Qt.ItemDataRole.UserRole)
        try:
            self._log = load_telemetry_csv(path)
        except (OSError, ValueError, KeyError) as exc:
            self._log = None
            self._meta.setText(f"Failed to load: {exc}")
            self._show_placeholder(str(exc))
            return

        self._meta.setText(
            f"{self._log.sample_count} samples · {self._log.duration_s:.1f} s · {self._log.path.name}"
        )
        self._render_plot()

    def _render_plot(self, _text: str | None = None) -> None:
        if self._log is None:
            return

        title = self._plot_combo.currentText()
        plot_fn = _PLOTS.get(title)
        if plot_fn is None:
            return

        self._figure.clear()
        with np.errstate(all="ignore"):
            plot_fn(self._figure, self._log)
        for ax in self._figure.axes:
            ax.set_facecolor("#1a1a1a")
            for spine in ax.spines.values():
                spine.set_color("#444444")
            ax.tick_params(colors="#aaaaaa")
            ax.xaxis.label.set_color("#cccccc")
            ax.yaxis.label.set_color("#cccccc")
            if hasattr(ax, "zaxis"):
                ax.zaxis.label.set_color("#cccccc")
            ax.title.set_color("#e0e0e0")
            ax.grid(True, alpha=0.35)

        self._figure.tight_layout()
        self._canvas.draw_idle()

    def _show_placeholder(self, message: str) -> None:
        self._figure.clear()
        ax = self._figure.add_subplot(111)
        ax.set_facecolor("#1a1a1a")
        ax.axis("off")
        ax.text(0.5, 0.5, message, ha="center", va="center", color="#888888", fontsize=11)
        self._canvas.draw_idle()
