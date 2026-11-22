from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from pingvault.styles import THEME


def make_tray_icon(size: int = 64) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(THEME["bg"]))
    painter.setPen(QColor(THEME["cyan"]))
    painter.drawRoundedRect(2, 2, size - 4, size - 4, 10, 10)
    painter.setPen(QColor(THEME["cyan"]))
    font = QFont("Bahnschrift", int(size * 0.28), QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pix.rect(), int(Qt.AlignmentFlag.AlignCenter), "PV")
    painter.end()
    return QIcon(pix)


def build_tray(parent, *, show_cb, boost_cb, quit_cb) -> QSystemTrayIcon:
    tray = QSystemTrayIcon(make_tray_icon(), parent)
    tray.setToolTip("PingVault")

    menu = QMenu(parent)
    act_show = QAction("顯示視窗", parent)
    act_show.triggered.connect(show_cb)
    act_boost = QAction("加速中心", parent)
    act_boost.triggered.connect(boost_cb)
    act_quit = QAction("結束並還原", parent)
    act_quit.triggered.connect(quit_cb)
    menu.addAction(act_show)
    menu.addAction(act_boost)
    menu.addSeparator()
    menu.addAction(act_quit)

    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: show_cb()
        if reason == QSystemTrayIcon.ActivationReason.Trigger
        else None
    )
    return tray
