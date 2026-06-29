"""Flight Analytics tab — plot telemetry CSV logs."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.collections import LineCollection
from matplotlib.figure import Figure
from matplotlib import cm
from matplotlib.ticker import FixedLocator, FormatStrFormatter, MaxNLocator
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

from telemetry_csv import (
    TelemetryLog,
    analyze_imu_fidelity,
    discover_telemetry_logs,
    load_telemetry_csv,
)

_PLOTS: dict[str, Callable[[Figure, TelemetryLog], None]] = {}


def _register_plot(title: str):
    def decorator(func: Callable[[Figure, TelemetryLog], None]):
        _PLOTS[title] = func
        return func

    return decorator


def _plot_title(label: str, n: int) -> str:
    return f"{label} (n = {n})"


def _nice_tick_step(span: float, *, min_step: float = 0.0) -> float:
    """Readable major tick step for an axis span (about six ticks)."""
    if span <= 0:
        return min_step or 1.0
    raw = span / 6.0
    magnitude = 10.0 ** np.floor(np.log10(raw))
    for mult in (1.0, 2.0, 2.5, 5.0, 10.0):
        step = mult * magnitude
        if step >= raw:
            return max(step, min_step)
    return max(10.0 * magnitude, min_step)


def _configure_axis_ticks(axis) -> None:
    vmin, vmax = axis.get_view_interval()
    span = abs(float(vmax - vmin))
    if not np.isfinite(span) or span <= 0:
        return

    if span < 1.0:
        step = _nice_tick_step(span, min_step=0.1)
        start = np.floor(vmin / step) * step
        end = np.ceil(vmax / step) * step
        ticks = np.arange(start, end + step * 0.5, step)
        if ticks.size == 0:
            ticks = np.array([float(vmin), float(vmax)])
        axis.set_major_locator(FixedLocator(ticks))
        axis.set_major_formatter(FormatStrFormatter("%.1f"))
    else:
        axis.set_major_locator(MaxNLocator(nbins="auto", integer=True, prune="both"))
        axis.set_major_formatter(FormatStrFormatter("%.0f"))


def _apply_adaptive_axis_ticks(fig: Figure) -> None:
    """Match tick precision to axis span; avoid duplicate integer labels on small ranges."""
    for ax in fig.get_axes():
        for axis in (ax.xaxis, ax.yaxis):
            _configure_axis_ticks(axis)
        if hasattr(ax, "zaxis"):
            _configure_axis_ticks(ax.zaxis)


def _velocity_gps_mask(log: TelemetryLog) -> np.ndarray:
    if log.format == "ground_station":
        return np.ones(log.sample_count, dtype=bool)
    mask = log.gps_unique_fix_mask()
    if not np.any(mask):
        mask = log.gps_event_mask()
    return mask


@_register_plot("Attitude")
def _plot_attitude(fig: Figure, log: TelemetryLog) -> None:
    mask = log.angle_mask()
    t, roll = log.series(mask, log.roll)
    _, pitch = log.series(mask, log.pitch)
    _, yaw = log.series(mask, log.yaw)

    ax = fig.add_subplot(111)
    if t.size == 0:
        ax.text(0.5, 0.5, "No attitude samples", ha="center", va="center", transform=ax.transAxes)
        return

    ax.plot(t, roll, label="Roll", color="#5dade2", linewidth=1.2)
    ax.plot(t, pitch, label="Pitch", color="#58d68d", linewidth=1.2)
    ax.plot(t, yaw, label="Yaw", color="#f5b041", linewidth=1.2)
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Angle [deg]")
    ax.set_title(
        f"Attitude vs Time ({log.plot_count_label(t.size, detail='fresh angle frames')})"
    )
    ax.grid(True, alpha=0.35)
    ax.legend(loc="upper right")


@_register_plot("Ground Track")
def _plot_ground_track(fig: Figure, log: TelemetryLog) -> None:
    _, east, north, alt_msl, _ = log.gps_track_series(dedupe=True)
    ax = fig.add_subplot(111)
    if east.size == 0:
        ax.text(0.5, 0.5, "No valid GPS fixes", ha="center", va="center", transform=ax.transAxes)
        return

    norm = cm.colors.Normalize(vmin=float(np.min(alt_msl)), vmax=float(np.max(alt_msl)))
    if east.size > 1:
        points = np.column_stack([east, north]).reshape(-1, 1, 2)
        segments = np.concatenate([points[:-1], points[1:]], axis=1)
        seg_alt = (alt_msl[:-1] + alt_msl[1:]) * 0.5
        lc = LineCollection(segments, cmap="viridis", norm=norm, linewidths=1.8, alpha=0.95)
        lc.set_array(seg_alt)
        ax.add_collection(lc)

    scatter = ax.scatter(east, north, c=alt_msl, cmap="viridis", norm=norm, s=14, zorder=3)
    ax.scatter(east[0], north[0], color="#58d68d", s=40, label="Start", zorder=5, edgecolors="white")
    ax.scatter(east[-1], north[-1], color="#ec7063", s=40, label="End", zorder=5, edgecolors="white")
    cbar = fig.colorbar(scatter, ax=ax, pad=0.02)
    cbar.set_label("Altitude [m]")
    ax.set_xlabel("Easting [m]")
    ax.set_ylabel("Northing [m]")
    ax.set_title(_plot_title("Ground Track - East vs North", east.size))
    ax.autoscale()
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True, alpha=0.35)
    ax.legend(loc="best")


@_register_plot("Distance vs Altitude")
def _plot_horiz_dist_vs_alt(fig: Figure, log: TelemetryLog) -> None:
    _, _, _, alt_msl, horiz_dist = log.gps_track_series(dedupe=True)
    ax = fig.add_subplot(111)
    if horiz_dist.size == 0:
        ax.text(0.5, 0.5, "No valid GPS fixes", ha="center", va="center", transform=ax.transAxes)
        return

    ax.plot(horiz_dist, alt_msl, color="#bb8fce", linewidth=1.5)
    ax.scatter(horiz_dist[0], alt_msl[0], color="#58d68d", s=40, label="Start", zorder=5)
    ax.scatter(horiz_dist[-1], alt_msl[-1], color="#ec7063", s=40, label="End", zorder=5)
    ax.set_xlabel("Horizontal Distance [m]")
    ax.set_ylabel("Altitude [m]")
    ax.set_title(_plot_title("Distance vs Altitude", horiz_dist.size))
    ax.grid(True, alpha=0.35)
    ax.legend(loc="best")


@_register_plot("3D Flight Path")
def _plot_3d_path(fig: Figure, log: TelemetryLog) -> None:
    _, east, north, alt_msl, _ = log.gps_track_series(dedupe=True)
    ax = fig.add_subplot(111, projection="3d")
    if east.size == 0:
        ax.text2D(0.5, 0.5, "No valid GPS fixes", transform=ax.transAxes, ha="center")
        return

    ax.plot(east, north, alt_msl, color="#5dade2", linewidth=1.5)
    ax.scatter(east[0], north[0], alt_msl[0], color="#58d68d", s=30, label="Start")
    ax.scatter(east[-1], north[-1], alt_msl[-1], color="#ec7063", s=30, label="End")
    ax.set_xlabel("Easting [m]")
    ax.set_ylabel("Northing [m]")
    ax.set_zlabel("Altitude [m]")
    ax.set_title(_plot_title("3D Path", east.size))
    ax.legend(loc="upper right")


@_register_plot("Acceleration vs time")
def _plot_acceleration(fig: Figure, log: TelemetryLog) -> None:
    mask = log.accel_mask()
    t, ax_ = log.series(mask, log.accel_x)
    _, ay = log.series(mask, log.accel_y)
    _, az = log.series(mask, log.accel_z)
    _, amag = log.series(mask, log.accel_mag)

    ax = fig.add_subplot(111)
    if t.size == 0:
        ax.text(0.5, 0.5, "No accelerometer samples", ha="center", va="center", transform=ax.transAxes)
        return

    ax.plot(t, ax_, label="Ax", color="#e74c3c", linewidth=1.0, alpha=0.85)
    ax.plot(t, ay, label="Ay", color="#58d68d", linewidth=1.0, alpha=0.85)
    ax.plot(t, az, label="Az", color="#5dade2", linewidth=1.0, alpha=0.85)
    ax.plot(t, amag, label="|A|", color="#f5b041", linewidth=1.4)
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Acceleration [m/s²]")
    ax.set_title(
        f"Acceleration vs Time ({log.plot_count_label(t.size, detail='fresh accel frames')})"
    )
    ax.grid(True, alpha=0.35)
    ax.legend(loc="upper right", ncol=2)


@_register_plot("Gyro vs time")
def _plot_gyro(fig: Figure, log: TelemetryLog) -> None:
    mask = log.gyro_mask()
    t, gx = log.series(mask, log.gyro_x)
    _, gy = log.series(mask, log.gyro_y)
    _, gz = log.series(mask, log.gyro_z)

    ax = fig.add_subplot(111)
    if t.size == 0:
        ax.text(0.5, 0.5, "No gyro samples", ha="center", va="center", transform=ax.transAxes)
        return

    ax.plot(t, gx, label="Gx", color="#e74c3c", linewidth=1.0, alpha=0.85)
    ax.plot(t, gy, label="Gy", color="#58d68d", linewidth=1.0, alpha=0.85)
    ax.plot(t, gz, label="Gz", color="#5dade2", linewidth=1.0, alpha=0.85)
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Angular rate [deg/s]")
    ax.set_title(
        f"Gyro vs Time ({log.plot_count_label(t.size, detail='fresh gyro frames')})"
    )
    ax.grid(True, alpha=0.35)
    ax.legend(loc="upper right")


@_register_plot("Velocity vs time")
def _plot_velocity(fig: Figure, log: TelemetryLog) -> None:
    gps_mask = _velocity_gps_mask(log)
    t, speed = log.series(gps_mask, log.speed)
    _, vn = log.series(gps_mask, log.vel_n)
    _, ve = log.series(gps_mask, log.vel_e)
    if np.any(np.abs(log.climb_rate) > 1e-6):
        _, climb = log.series(gps_mask, log.climb_rate)
    else:
        _, climb = log.series(gps_mask, -log.vel_d)

    ax = fig.add_subplot(111)
    if t.size == 0:
        ax.text(0.5, 0.5, "No velocity samples", ha="center", va="center", transform=ax.transAxes)
        return

    ax.plot(t, speed, label="Ground speed", color="#f5b041", linewidth=1.4)

    has_ned = np.any(np.abs(vn) > 1e-6) or np.any(np.abs(ve) > 1e-6)
    if has_ned:
        ax.plot(t, vn, label="V north", color="#58d68d", linewidth=1.0, alpha=0.85)
        ax.plot(t, ve, label="V east", color="#5dade2", linewidth=1.0, alpha=0.85)

    has_climb = np.any(np.abs(climb) > 1e-6)
    if has_climb:
        ax.plot(t, climb, label="Climb (+up)", color="#ec7063", linewidth=1.0, alpha=0.85)

    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Velocity [m/s]")
    ax.set_title(_plot_title("Velocity vs Time", t.size))
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

        plot_section = QFrame()
        plot_section.setStyleSheet(
            """
            QFrame {
                background-color: #151515;
                border: 1px solid #2a2a2a;
                border-radius: 4px;
            }
            """
        )
        plot_section_layout = QVBoxLayout(plot_section)
        plot_section_layout.setContentsMargins(10, 10, 10, 10)
        plot_section_layout.setSpacing(6)

        plot_label = QLabel("Plot type")
        plot_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        plot_section_layout.addWidget(plot_label)

        self._plot_combo = QComboBox()
        self._plot_combo.addItems(list(_PLOTS.keys()))
        self._plot_combo.currentTextChanged.connect(self._render_plot)
        plot_section_layout.addWidget(self._plot_combo)
        top_layout.addWidget(plot_section)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Plain)
        separator.setStyleSheet("color: #333333; background-color: #333333; max-height: 1px;")
        top_layout.addWidget(separator)

        logs_section = QFrame()
        logs_section.setStyleSheet("QFrame { background-color: transparent; border: none; }")
        logs_section_layout = QVBoxLayout(logs_section)
        logs_section_layout.setContentsMargins(0, 4, 0, 0)
        logs_section_layout.setSpacing(6)

        logs_label = QLabel("Telemetry logs")
        logs_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        logs_section_layout.addWidget(logs_label)

        self._file_list = QListWidget()
        self._file_list.setMaximumHeight(120)
        self._file_list.currentItemChanged.connect(self._on_file_selected)
        logs_section_layout.addWidget(self._file_list)

        btn_row = QHBoxLayout()
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self.refresh_file_list)
        self._browse_btn = QPushButton("Browse…")
        self._browse_btn.clicked.connect(self._browse_file)
        btn_row.addWidget(self._refresh_btn)
        btn_row.addWidget(self._browse_btn)
        btn_row.addStretch()
        logs_section_layout.addLayout(btn_row)

        self._meta = QLabel("Select a log file")
        self._meta.setWordWrap(True)
        self._meta.setStyleSheet("color: #888888;")
        logs_section_layout.addWidget(self._meta)

        top_layout.addWidget(logs_section)

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

        fidelity = analyze_imu_fidelity(self._log)
        fmt_label = {
            "avionics": "onboard avionics",
            "ground_station": "ground-station snapshot",
            "legacy": "legacy CSV",
        }.get(self._log.format, self._log.format)

        self._meta.setText(
            f"{self._log.sample_count} rows · {self._log.duration_s:.1f} s · "
            f"{fmt_label} · {self._log.path.name} · {fidelity.summary}"
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

        _apply_adaptive_axis_ticks(self._figure)

        self._figure.tight_layout()
        self._canvas.draw_idle()

    def _show_placeholder(self, message: str) -> None:
        self._figure.clear()
        ax = self._figure.add_subplot(111)
        ax.set_facecolor("#1a1a1a")
        ax.axis("off")
        ax.text(0.5, 0.5, message, ha="center", va="center", color="#888888", fontsize=11)
        self._canvas.draw_idle()
