from __future__ import annotations

import math

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRectF, Qt, Property
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygon
from PySide6.QtWidgets import QFrame, QLabel, QProgressBar, QVBoxLayout, QWidget

from pingvault.styles import THEME


class StatChip(QFrame):
    """HUD metric tile: label / value / optional sub / slim signal bar."""

    def __init__(self, label: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("StatChip")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        self._label = QLabel(label.upper())
        self._label.setObjectName("MetricLabel")
        self._value = QLabel("--")
        self._value.setObjectName("MetricValue")
        self._sub = QLabel("")
        self._sub.setObjectName("Muted")
        self._sub.setStyleSheet(
            f"color:{THEME['muted_dim']}; font-size:10px; font-weight:600;"
        )
        self._bar = QProgressBar()
        self._bar.setObjectName("SlimBar")
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(False)

        layout.addWidget(self._label)
        layout.addWidget(self._value)
        layout.addWidget(self._sub)
        layout.addWidget(self._bar)

    def set_value(
        self,
        text: str,
        percent: int | None = None,
        color: str | None = None,
        sub: str | None = None,
    ) -> None:
        self._value.setText(text)
        if sub is None:
            self._sub.setText("")
            self._sub.hide()
        else:
            self._sub.setText(sub)
            self._sub.show()
        if percent is not None:
            self._bar.setValue(max(0, min(100, percent)))
        if color:
            self._bar.setStyleSheet(
                "QProgressBar#SlimBar{background:#121C2E;border:none;border-radius:1px;"
                "max-height:3px;min-height:3px;}"
                f"QProgressBar::chunk, QProgressBar#SlimBar::chunk{{background:{color};border-radius:1px;}}"
            )


class SpeedGauge(QWidget):
    """Instrument-style realtime speed ring with eased fill."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(180, 180)
        self._down_bps: float = 0.0
        self._up_bps: float = 0.0
        self._down_text = "—"
        self._up_text = "—"
        self._progress = 0.08
        self._anim = QPropertyAnimation(self, b"progress", self)
        self._anim.setDuration(420)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _get_progress(self) -> float:
        return self._progress

    def _set_progress(self, value: float) -> None:
        self._progress = max(0.0, min(1.0, value))
        self.update()

    progress = Property(float, _get_progress, _set_progress)

    def set_speed(self, down_bps: float, up_bps: float, down_text: str, up_text: str) -> None:
        self._down_bps = max(0.0, down_bps)
        self._up_bps = max(0.0, up_bps)
        self._down_text = down_text
        self._up_text = up_text

        mbps = (self._down_bps * 8.0) / 1_000_000.0
        target = max(0.08, min(1.0, mbps / 100.0 if mbps > 0 else 0.08))
        self._anim.stop()
        self._anim.setStartValue(self._progress)
        self._anim.setEndValue(target)
        self._anim.start()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        side = min(self.width(), self.height())
        cx = self.width() / 2
        cy = self.height() / 2
        outer = QRectF(cx - side / 2 + 8, cy - side / 2 + 8, side - 16, side - 16)
        rect = outer.adjusted(10, 10, -10, -10)

        tick_pen = QPen(QColor(THEME["hud_line"]), 1.5)
        painter.setPen(tick_pen)
        for i in range(48):
            angle = math.radians(i * (360 / 48) - 90)
            inner_r = (outer.width() / 2) - (7 if i % 4 == 0 else 3)
            outer_r = outer.width() / 2
            x1 = cx + math.cos(angle) * inner_r
            y1 = cy + math.sin(angle) * inner_r
            x2 = cx + math.cos(angle) * outer_r
            y2 = cy + math.sin(angle) * outer_r
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        track = QPen(QColor("#152238"), 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap)
        painter.setPen(track)
        painter.drawArc(rect, 0, 360 * 16)

        mbps = (self._down_bps * 8.0) / 1_000_000.0
        if mbps < 5:
            color = QColor(THEME["accent"])
        elif mbps < 40:
            color = QColor(THEME["success"])
        else:
            color = QColor(THEME["cyan"])

        pen = QPen(color, 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        painter.drawArc(rect, 90 * 16, int(-360 * 16 * self._progress))

        hair = QPen(QColor(THEME["cyan_dim"]), 1)
        painter.setPen(hair)
        painter.drawEllipse(rect.adjusted(16, 16, -16, -16))

        top_band = QRectF(rect.left(), rect.top() + rect.height() * 0.22, rect.width(), 16)
        value_band = QRectF(rect.left(), rect.top() + rect.height() * 0.36, rect.width(), 34)
        up_band = QRectF(rect.left(), rect.top() + rect.height() * 0.62, rect.width(), 18)

        painter.setPen(QColor(THEME["cyan"]))
        top_font = QFont()
        top_font.setFamilies(["Bahnschrift", "Microsoft JhengHei UI"])
        top_font.setPointSize(8)
        top_font.setWeight(QFont.Weight.Bold)
        painter.setFont(top_font)
        painter.drawText(
            top_band,
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
            "DOWNLINK",
        )

        painter.setPen(QColor(THEME["text"]))
        value_font = QFont()
        value_font.setFamilies(["Cascadia Mono", "Consolas", "Bahnschrift"])
        value_font.setPointSize(16)
        value_font.setWeight(QFont.Weight.Bold)
        painter.setFont(value_font)
        painter.drawText(
            value_band,
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
            self._down_text,
        )

        painter.setPen(QColor(THEME["muted"]))
        bottom_font = QFont()
        bottom_font.setFamilies(["Bahnschrift", "Microsoft JhengHei UI"])
        bottom_font.setPointSize(8)
        bottom_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(bottom_font)
        painter.drawText(
            up_band,
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
            f"UPLINK  {self._up_text}",
        )


PingGauge = SpeedGauge


class AtmosphereBackground(QWidget):
    """Tactical stage: deep navy, faint grid, diagonal signal wash."""

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        painter.fillRect(self.rect(), QColor(THEME["bg"]))

        glow = QColor(THEME["accent"])
        glow.setAlpha(22)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(-120, -160, 480, 400)

        cyan = QColor(THEME["cyan"])
        cyan.setAlpha(16)
        painter.setBrush(cyan)
        painter.drawEllipse(w - 420, h - 360, 500, 460)

        painter.setPen(QPen(QColor(53, 208, 255, 12), 1))
        step = 48
        for x in range(0, w, step):
            painter.drawLine(x, 0, x, h)
        for y in range(0, h, step):
            painter.drawLine(0, y, w, y)

        band = QColor(53, 208, 255, 10)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(band)
        painter.drawPolygon(
            QPolygon(
                [
                    QPoint(w, 0),
                    QPoint(w - 280, 0),
                    QPoint(w - 80, h),
                    QPoint(w, h),
                ]
            )
        )
