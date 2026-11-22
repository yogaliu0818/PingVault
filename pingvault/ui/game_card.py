from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from pingvault.services.games import Game
from pingvault.services.icons import load_cover
from pingvault.styles import THEME


class GameCard(QWidget):
    """Cover-forward tactical card. No StaticContents — avoids scroll ghosts."""

    clicked = Signal(object)

    WIDTH = 168
    HEIGHT = 248
    COVER_W = 156
    COVER_H = 220

    def __init__(self, game: Game, parent=None) -> None:
        super().__init__(parent)
        self.game = game
        self._selected = False
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor(THEME["bg"]))
        self.setPalette(palette)
        self._buffer = self._build_buffer(selected=False)

    def set_selected(self, selected: bool) -> None:
        if self._selected == selected:
            return
        self._selected = selected
        self._buffer = self._build_buffer(selected=selected)
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.game)
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor(THEME["bg"]))
        painter.drawPixmap(0, 0, self._buffer)

    def _build_buffer(self, selected: bool) -> QPixmap:
        pixmap = QPixmap(self.WIDTH, self.HEIGHT)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        cover_x = (self.WIDTH - self.COVER_W) // 2
        cover_y = 4
        card_path = QPainterPath()
        card_path.addRoundedRect(cover_x - 1, cover_y - 1, self.COVER_W + 2, self.COVER_H + 2, 4, 4)

        painter.fillPath(card_path, QColor(THEME["panel_alt"]))
        border = QColor(THEME["cyan"] if selected else THEME["border"])
        painter.setPen(QPen(border, 2 if selected else 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(card_path)

        if selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(THEME["cyan"]))
            painter.drawRect(cover_x - 1, cover_y + 18, 3, self.COVER_H - 36)

        clip = QPainterPath()
        clip.addRoundedRect(cover_x, cover_y, self.COVER_W, self.COVER_H, 3, 3)
        painter.setClipPath(clip)
        cover = load_cover(self.game.id, self.COVER_W, self.COVER_H)
        if cover is not None:
            painter.drawPixmap(cover_x, cover_y, cover)
        else:
            painter.fillRect(cover_x, cover_y, self.COVER_W, self.COVER_H, QColor(self.game.color))

        # Bottom gradient for title legibility
        grad = QLinearGradient(0, cover_y + self.COVER_H - 70, 0, cover_y + self.COVER_H)
        grad.setColorAt(0, QColor(5, 8, 15, 0))
        grad.setColorAt(0.45, QColor(5, 8, 15, 180))
        grad.setColorAt(1, QColor(5, 8, 15, 230))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grad)
        painter.drawRect(cover_x, cover_y + self.COVER_H - 70, self.COVER_W, 70)
        painter.setClipping(False)

        painter.setPen(QColor(THEME["text"]))
        title_font = QFont()
        title_font.setFamilies(["Bahnschrift", "Microsoft JhengHei UI"])
        title_font.setPointSize(10)
        title_font.setWeight(QFont.Weight.Bold)
        painter.setFont(title_font)
        painter.drawText(
            cover_x + 8,
            cover_y + self.COVER_H - 48,
            self.COVER_W - 16,
            28,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap),
            self.game.name,
        )

        painter.setPen(QColor(THEME["cyan"] if selected else THEME["muted_dim"]))
        genre_font = QFont()
        genre_font.setFamilies(["Bahnschrift", "Microsoft JhengHei UI"])
        genre_font.setPointSize(8)
        genre_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(genre_font)
        painter.drawText(
            cover_x + 8,
            cover_y + self.COVER_H - 18,
            self.COVER_W - 16,
            14,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            self.game.genre.upper(),
        )
        painter.end()
        return pixmap
