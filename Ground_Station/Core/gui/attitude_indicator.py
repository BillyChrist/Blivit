"""Artificial horizon / attitude indicator + attitude readout."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PyQt6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from gui.comms_panel import CommsStatusPanel


class AttitudeReadout(QFrame):
    """Centered roll / pitch / yaw display below the horizon."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("attitudeReadout")
        self.setStyleSheet(
            """
            QFrame#attitudeReadout {
                background-color: #1e1e1e;
                border: 1px solid #444444;
                border-radius: 6px;
                padding: 8px 16px;
            }
            """
        )

        grid = QGridLayout(self)
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(4)

        font_title = QFont("Segoe UI", 9)
        font_title.setBold(True)
        font_value = QFont("Consolas", 14)
        font_value.setBold(True)

        self._values: dict[str, QLabel] = {}
        for col, (key, title) in enumerate(
            (("roll", "ROLL"), ("pitch", "PITCH"), ("yaw", "YAW"))
        ):
            name = QLabel(title)
            name.setFont(font_title)
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name.setStyleSheet("color: #888888; border: none;")
            value = QLabel("+0.00°")
            value.setFont(font_value)
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value.setStyleSheet("color: #f0f0f0; border: none;")
            grid.addWidget(name, 0, col)
            grid.addWidget(value, 1, col)
            self._values[key] = value

    def set_attitude(self, roll: float, pitch: float, yaw: float) -> None:
        self._values["roll"].setText(f"{roll:+.2f}°")
        self._values["pitch"].setText(f"{pitch:+.2f}°")
        self._values["yaw"].setText(f"{yaw:+.2f}°")


class AttitudeIndicator(QWidget):
    """Artificial horizon — WitMotion roll/pitch axes swapped for correct display."""

    _HEADING_HEIGHT = 36
    _TOP_MARGIN = 78
    _BOTTOM_MARGIN = 12
    _SIDE_MARGIN = 16

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._roll = 0.0
        self._pitch = 0.0
        self._yaw = 0.0
        self.setMinimumSize(300, 360)

    def set_attitude(self, roll: float, pitch: float, yaw: float) -> None:
        self._roll = roll
        self._pitch = pitch
        self._yaw = yaw
        self.update()

    def _display_bank(self) -> float:
        """Bank angle for horizon rotation (WitMotion pitch axis)."""
        return self._pitch

    def _display_elevation(self) -> float:
        """Elevation for horizon shift (WitMotion roll axis)."""
        return self._roll

    def paintEvent(self, _event) -> None:
        if self.width() < 40 or self.height() < 40:
            return

        painter = QPainter(self)
        if not painter.isActive():
            return

        try:
            self._paint_horizon(painter)
        finally:
            painter.end()

    def _paint_horizon(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2

        avail_h = h - self._TOP_MARGIN - self._BOTTOM_MARGIN
        avail_w = w - 2 * self._SIDE_MARGIN
        radius = min(avail_w, avail_h) * 0.46
        if radius < 20:
            return
        cy = self._TOP_MARGIN + avail_h / 2

        bank = self._display_bank()
        elevation = self._display_elevation()

        painter.fillRect(self.rect(), QColor("#1a1a1a"))

        self._draw_heading_strip(painter, w, cx, radius, cy)

        painter.save()
        painter.setClipPath(self._circle_path(cx, cy, radius))
        painter.translate(cx, cy)
        painter.rotate(-bank)

        pitch_px = elevation * (radius / 45.0)
        sky_h = radius * 2
        painter.fillRect(
            int(-radius * 2), int(-radius * 2 + pitch_px), int(radius * 4), int(sky_h), QColor("#2f6db0")
        )
        painter.fillRect(int(-radius * 2), int(pitch_px), int(radius * 4), int(sky_h), QColor("#6b4a2e"))

        painter.setPen(QPen(QColor("#f0f0f0"), 2))
        painter.drawLine(int(-radius * 1.2), int(pitch_px), int(radius * 1.2), int(pitch_px))

        painter.setPen(QPen(QColor("#d8d8d8"), 1))
        for deg in range(-30, 35, 10):
            if deg == 0:
                continue
            y = pitch_px - deg * (radius / 45.0)
            half = radius * 0.35 if deg % 20 == 0 else radius * 0.18
            painter.drawLine(int(-half), int(y), int(half), int(y))
            if deg % 20 == 0:
                painter.drawText(int(half + 4), int(y + 4), f"{abs(deg)}")

        painter.restore()

        painter.setPen(QPen(QColor("#888888"), 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(int(cx - radius), int(cy - radius), int(radius * 2), int(radius * 2))

        painter.save()
        painter.translate(cx, cy)
        painter.setPen(QPen(QColor("#ffcc00"), 3))
        painter.drawLine(int(-radius * 0.55), 0, int(-radius * 0.12), 0)
        painter.drawLine(int(radius * 0.12), 0, int(radius * 0.55), 0)
        painter.drawLine(0, 0, 0, int(radius * 0.08))
        painter.restore()

        self._draw_roll_scale(painter, cx, cy, radius, bank)

    def _draw_heading_strip(
        self, painter: QPainter, w: int, cx: float, radius: float, cy: float
    ) -> None:
        """Scrolling heading tape — fixed lubber mark at center, tape moves with yaw."""
        strip_w = min(radius * 1.35, w / 2 - self._SIDE_MARGIN)
        strip_y = 4
        label_h = 14
        tape_y = strip_y + label_h + 2
        tape_h = self._HEADING_HEIGHT - label_h - 2
        strip_left = cx - strip_w
        strip_right = cx + strip_w

        painter.fillRect(
            int(strip_left), tape_y, int(strip_w * 2), tape_h, QColor("#1e1e1e")
        )
        painter.setPen(QPen(QColor("#444444"), 1))
        painter.drawRect(int(strip_left), tape_y, int(strip_w * 2), tape_h)

        yaw = self._yaw % 360.0
        px_per_deg = strip_w / 35.0

        font_label = QFont("Consolas", 9)
        font_label.setBold(True)
        painter.setFont(font_label)
        fm = QFontMetrics(font_label)

        painter.save()
        painter.setClipRect(QRectF(strip_left + 1, tape_y + 1, strip_w * 2 - 2, tape_h - 2))

        center_tick = int(yaw // 5) * 5
        for h in range(center_tick - 45, center_tick + 50, 5):
            heading = h % 360
            delta = heading - yaw
            if delta > 180.0:
                delta -= 360.0
            elif delta < -180.0:
                delta += 360.0

            x = cx + delta * px_per_deg
            if x < strip_left + 6 or x > strip_right - 6:
                continue

            is_major = heading % 10 == 0
            tick_top = tape_y + 3
            tick_bot = tape_y + tape_h - (10 if is_major else 5)
            painter.setPen(QPen(QColor("#aaaaaa" if is_major else "#666666"), 1))
            painter.drawLine(int(x), tick_top, int(x), tick_bot)

            if is_major and strip_left + 20 < x < strip_right - 20:
                text = f"{heading:03d}"
                text_w = fm.horizontalAdvance(text)
                text_rect = QRectF(x - text_w / 2, strip_y, text_w, label_h)
                painter.setPen(QColor("#e8e8e8"))
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, text)

        painter.restore()

        # Fixed lubber line + pointer (aircraft reference)
        painter.setPen(QPen(QColor("#ff4444"), 2))
        lubber_top = tape_y - 1
        lubber_bot = tape_y + tape_h + 1
        painter.drawLine(int(cx), lubber_top, int(cx), lubber_bot)

        tri = QPolygonF(
            [
                QPointF(cx, lubber_bot + 1),
                QPointF(cx - 6, lubber_bot + 9),
                QPointF(cx + 6, lubber_bot + 9),
            ]
        )
        painter.setBrush(QColor("#ff4444"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(tri)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Digital heading under lubber line
        heading_text = f"{yaw:05.1f}°"
        font_hdg = QFont("Consolas", 10)
        font_hdg.setBold(True)
        painter.setFont(font_hdg)
        hdg_w = QFontMetrics(font_hdg).horizontalAdvance(heading_text)
        hdg_rect = QRectF(cx - hdg_w / 2 - 4, lubber_bot + 10, hdg_w + 8, 16)
        painter.fillRect(hdg_rect, QColor("#2a2a2a"))
        painter.setPen(QPen(QColor("#555555"), 1))
        painter.drawRect(hdg_rect)
        painter.setPen(QColor("#ffcc00"))
        painter.drawText(hdg_rect, Qt.AlignmentFlag.AlignCenter, heading_text)

    @staticmethod
    def _circle_path(cx: float, cy: float, radius: float) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(cx - radius, cy - radius, radius * 2, radius * 2)
        return path

    def _draw_roll_scale(
        self, painter: QPainter, cx: float, cy: float, radius: float, bank: float
    ) -> None:
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(-bank)
        painter.setPen(QPen(QColor("#ffcc00"), 2))
        painter.drawLine(0, int(-radius * 0.78), 0, int(-radius * 0.62))
        painter.restore()

        painter.setPen(QPen(QColor("#aaaaaa"), 2))
        for deg in (-60, -30, 30, 60):
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(deg)
            painter.drawLine(0, int(-radius * 0.92), 0, int(-radius * 0.82))
            painter.restore()


class AttitudeDisplay(QWidget):
    """Comms status, horizon, and attitude readout."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.comms = CommsStatusPanel()
        self._indicator = AttitudeIndicator()
        self._readout = AttitudeReadout()

        layout.addWidget(self.comms, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._indicator, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._readout, alignment=Qt.AlignmentFlag.AlignCenter)

    @property
    def logging_toggled(self):
        return self.comms.logging_toggled

    def set_logging_state(self, active: bool, filepath: str = "") -> None:
        self.comms.set_logging_state(active, filepath)

    def set_attitude(self, roll: float, pitch: float, yaw: float) -> None:
        self._indicator.set_attitude(roll, pitch, yaw)
        self._readout.set_attitude(roll, pitch, yaw)

    def update_comms(
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
        self.comms.update_status(
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
