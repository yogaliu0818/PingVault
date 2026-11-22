from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pingvault.services.admin import ADMIN_HELP, is_admin
from pingvault.services.fps import FpsSample
from pingvault.services.games import Game, GameCatalog
from pingvault.services.network import PingResult
from pingvault.services.optimizer import (
    BoostResult,
    BoostStatus,
    ProcessInfo,
    ThrottleCandidate,
)
from pingvault.services.performance import SystemStats
from pingvault.services.icons import load_cover, warm_cover_cache
from pingvault.services.profiles import profile_for
from pingvault.services.net_speed import NetSpeedMonitor, NetSpeedStats
from pingvault.services.session_compare import MetricPair, SessionCompare
from pingvault.services.thermal import ThermalStats
from pingvault.services.user_prefs import PrefsStore
from pingvault.styles import APP_STYLESHEET, THEME
from pingvault.ui.game_card import GameCard
from pingvault.ui.tray import build_tray
from pingvault.ui.widgets import AtmosphereBackground, SpeedGauge, StatChip
from pingvault.ui.workers import MonitorWorker, PingWorker


class MainWindow(QMainWindow):
    request_stats = Signal()
    request_processes = Signal()
    request_throttle = Signal(object)
    request_ping = Signal(object)
    request_boost = Signal(object, object)
    request_maintain = Signal()
    request_stop_boost = Signal()
    request_recovery = Signal()
    request_pause_enabled = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PingVault")
        self.resize(1380, 880)
        self.setMinimumSize(1180, 740)
        self.setStyleSheet(APP_STYLESHEET)

        self.catalog = GameCatalog()
        self.selected_game: Game | None = None
        self._cards: list[GameCard] = []
        self._boosted = False
        self._boost_armed = False
        self._boost_inflight = False
        self._stop_requested = False
        self._stop_queued = False
        self._expecting_boost = False
        self._force_quit = False
        self._shutdown_done = False
        self._ping_busy = False
        self._net_speed = NetSpeedMonitor()
        self._last_cpu = 0.0
        self._last_fps: float | None = None
        self._last_ping_ms: float | None = None
        self._fps_status = "FPS：尚未偵測 RTSS"
        self._is_admin = is_admin()
        self._prefs = PrefsStore()
        self._compare = SessionCompare.empty()
        self._compare_live = False
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(120)
        self._search_timer.timeout.connect(self._apply_search)

        self._worker_thread = QThread()
        self._worker = MonitorWorker()
        self._worker.moveToThread(self._worker_thread)

        self._ping_thread = QThread()
        self._ping_worker = PingWorker()
        self._ping_worker.moveToThread(self._ping_thread)

        self.request_stats.connect(self._worker.sample_stats)
        self.request_processes.connect(self._worker.sample_processes)
        self.request_throttle.connect(self._worker.sample_throttle)
        self.request_boost.connect(self._worker.boost_game)
        self.request_maintain.connect(self._worker.maintain_boost)
        self.request_stop_boost.connect(self._worker.stop_boost)
        self.request_ping.connect(self._ping_worker.ping_game)
        self.request_recovery.connect(self._worker.emit_recovery)
        self.request_pause_enabled.connect(self._worker.set_pause_enabled)

        self._worker.stats_ready.connect(self._on_stats)
        self._worker.thermal_ready.connect(self._on_thermal)
        self._worker.processes_ready.connect(self._on_processes)
        self._worker.throttle_ready.connect(self._on_throttle)
        self._worker.boost_ready.connect(self._on_boost)
        self._worker.maintain_ready.connect(self._on_maintain)
        self._worker.fps_ready.connect(self._on_fps)
        self._worker.recovery_ready.connect(self._on_recovery)
        self._ping_worker.ping_ready.connect(self._on_ping)

        self._worker_thread.start()
        self._ping_thread.start()
        # Build small JPEG thumbs once so scrolling never rescales multi‑MB covers.
        warm_cover_cache([game.id for game in self.catalog.all()])
        self._build_ui()
        self._build_game_cards(self.catalog.all())
        self._relayout_cards(self.catalog.all())

        self._stats_timer = QTimer(self)
        self._stats_timer.setInterval(1500)
        self._stats_timer.timeout.connect(self.request_stats.emit)
        self._stats_timer.start()

        # Sample NIC on UI thread so boost/ping never stretch the speed window.
        self._speed_timer = QTimer(self)
        self._speed_timer.setInterval(1000)
        self._speed_timer.timeout.connect(self._poll_speed)
        self._speed_timer.start()

        self._proc_timer = QTimer(self)
        self._proc_timer.setInterval(4000)
        self._proc_timer.timeout.connect(self.request_processes.emit)
        self._proc_timer.start()

        self._throttle_timer = QTimer(self)
        self._throttle_timer.setInterval(5000)
        self._throttle_timer.timeout.connect(self._refresh_throttle)

        self._arm_timer = QTimer(self)
        self._arm_timer.setInterval(3000)
        self._arm_timer.timeout.connect(self._retry_armed_boost)

        self._maintain_timer = QTimer(self)
        self._maintain_timer.setInterval(2500)
        self._maintain_timer.timeout.connect(self.request_maintain.emit)

        self._stop_watchdog = QTimer(self)
        self._stop_watchdog.setSingleShot(True)
        self._stop_watchdog.setInterval(6000)
        self._stop_watchdog.timeout.connect(self._force_stop_ui)

        self.request_stats.emit()
        self.request_processes.emit()
        self._poll_speed()
        self.request_recovery.emit()
        self._render_compare()
        self._setup_tray()

    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return
        self.tray = build_tray(
            self,
            show_cb=self._show_from_tray,
            boost_cb=lambda: (self._show_from_tray(), self._switch_page(0, self.nav_boost)),
            quit_cb=self._quit_from_tray,
        )
        self.tray.show()
        self.tray.showMessage(
            "PingVault",
            "已常駐系統匣。關閉視窗會縮到托盤，不會直接結束。",
            QSystemTrayIcon.MessageIcon.Information,
            3500,
        )

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_from_tray(self) -> None:
        self._force_quit = True
        self.shutdown_restore()
        self.close()

    def shutdown_restore(self) -> None:
        """Stop boost + wake paused apps. Safe to call multiple times."""
        if self._shutdown_done:
            return
        self._shutdown_done = True
        try:
            self._arm_timer.stop()
            self._maintain_timer.stop()
            self._stop_watchdog.stop()
        except Exception:
            pass
        try:
            self._worker.mark_stop()
        except Exception:
            pass
        # Resume suspended apps first (same order as stop_boost).
        try:
            self._worker._pause.resume_all()  # noqa: SLF001
        except Exception:
            pass
        try:
            self._worker._opt.stop_boost()  # noqa: SLF001
        except Exception:
            pass
        try:
            from pingvault.services.session_restore import restore_all

            restore_all()
        except Exception:
            pass

    def changeEvent(self, event) -> None:  # noqa: N802
        if (
            event.type() == QEvent.Type.WindowStateChange
            and self.isMinimized()
            and getattr(self, "tray", None) is not None
        ):
            event.accept()
            QTimer.singleShot(0, self.hide)
            self.tray.showMessage(
                "PingVault",
                "仍在背景監測／待命中。點托盤圖示可叫回視窗。",
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )
            return
        super().changeEvent(event)

    def _build_ui(self) -> None:
        root = AtmosphereBackground()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_sidebar())
        layout.addWidget(self._build_main(), 1)

    def _build_sidebar(self) -> QFrame:
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(232)
        col = QVBoxLayout(side)
        col.setContentsMargins(20, 28, 20, 24)
        col.setSpacing(6)

        brand_wrap = QVBoxLayout()
        brand_wrap.setSpacing(2)
        brand_row = QHBoxLayout()
        brand_row.setSpacing(0)
        ping = QLabel("Ping")
        ping.setObjectName("Brand")
        vault = QLabel("Vault")
        vault.setObjectName("BrandAccent")
        brand_row.addWidget(ping)
        brand_row.addWidget(vault)
        brand_row.addStretch(1)
        brand_wrap.addLayout(brand_row)

        tag = QLabel("TACTICAL NET · LOCAL BOOST")
        tag.setStyleSheet(
            f"color:{THEME['muted_dim']}; font-size:10px; font-weight:700; "
            "letter-spacing:1.6px; margin-bottom:18px;"
        )
        brand_wrap.addWidget(tag)
        col.addLayout(brand_wrap)

        self.nav_boost = self._nav_button("加速中心", True)
        self.nav_monitor = self._nav_button("效能監測")
        self.nav_boost.clicked.connect(lambda: self._switch_page(0, self.nav_boost))
        self.nav_monitor.clicked.connect(lambda: self._switch_page(1, self.nav_monitor))

        col.addWidget(self.nav_boost)
        col.addWidget(self.nav_monitor)
        col.addStretch(1)

        tip = QLabel("選遊戲 → 測速 → Boost\n優先優化本機效能與延遲監測")
        tip.setWordWrap(True)
        tip.setStyleSheet(f"color:{THEME['muted_dim']}; font-size:11px; line-height:1.4;")
        col.addWidget(tip)
        return side

    def _nav_button(self, text: str, active: bool = False) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("NavButton")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setProperty("active", "true" if active else "false")
        return btn

    def _switch_page(self, index: int, active_btn: QPushButton) -> None:
        self.stack.setCurrentIndex(index)
        for btn in (self.nav_boost, self.nav_monitor):
            btn.setProperty("active", "true" if btn is active_btn else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _build_main(self) -> QWidget:
        wrap = QWidget()
        col = QVBoxLayout(wrap)
        col.setContentsMargins(28, 26, 28, 26)
        col.setSpacing(16)

        col.addWidget(self._build_stat_strip())

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_boost_page())
        self.stack.addWidget(self._build_monitor_page())
        col.addWidget(self.stack, 1)
        return wrap

    def _build_stat_strip(self) -> QFrame:
        """
        Top strip layout:
        [CPU % + °C] [GPU °C] [RAM] [DISK] | [PING] [LOSS]
        Thermals stay with system load; network stays on the right.
        """
        strip = QFrame()
        strip.setObjectName("StatStrip")
        row = QHBoxLayout(strip)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(4)

        self.cpu_chip = StatChip("CPU")
        self.gpu_chip = StatChip("GPU")
        self.mem_chip = StatChip("記憶體")
        self.disk_chip = StatChip("磁碟")
        self.ping_chip = StatChip("延遲")
        self.loss_chip = StatChip("丟包")

        for chip in (
            self.cpu_chip,
            self.gpu_chip,
            self.mem_chip,
            self.disk_chip,
            self.ping_chip,
            self.loss_chip,
        ):
            row.addWidget(chip, 1)

        # Placeholder until first thermal sample arrives.
        self.gpu_chip.set_value("--", 0, THEME["muted_dim"], sub="等待讀溫")
        self._last_cpu_percent = 0
        return strip

    def _build_boost_page(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        left = QVBoxLayout()
        left.setSpacing(14)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        title = QLabel("選擇要加速的遊戲")
        title.setObjectName("SectionTitle")
        hint = QLabel("點選遊戲，右側會顯示延遲環與一鍵 Boost")
        hint.setObjectName("Muted")
        title_col.addWidget(title)
        title_col.addWidget(hint)
        header.addLayout(title_col, 1)

        self.search = QLineEdit()
        self.search.setObjectName("SearchBox")
        self.search.setPlaceholderText("搜尋：原神、FPS、CS2…")
        self.search.setFixedWidth(280)
        self.search.setClearButtonEnabled(True)
        self.search.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.search.textChanged.connect(self._on_search_text)
        self.search.returnPressed.connect(self._apply_search)
        header.addWidget(self.search, 0, Qt.AlignmentFlag.AlignTop)
        left.addLayout(header)

        self.search_status = QLabel("")
        self.search_status.setObjectName("Muted")
        left.addWidget(self.search_status)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea{{background:{THEME['bg']}; border:none;}}"
            f"QScrollArea>QWidget>QWidget{{background:{THEME['bg']};}}"
        )
        self.game_scroll = scroll

        self.game_grid_host = QWidget()
        self.game_grid_host.setStyleSheet(f"background:{THEME['bg']};")
        self.game_rows = QVBoxLayout(self.game_grid_host)
        self.game_rows.setContentsMargins(0, 4, 8, 12)
        self.game_rows.setSpacing(16)
        self.game_rows.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        # Park filtered-out cards here so they cannot paint inside the scroll view.
        self._card_park = QWidget()
        self._card_park.hide()

        scroll.setWidget(self.game_grid_host)
        left.addWidget(scroll, 1)

        layout.addLayout(left, 5)
        layout.addWidget(self._build_boost_panel(), 3)
        return page

    def _build_boost_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("HeroPanel")
        panel.setFixedWidth(380)
        root = QVBoxLayout(panel)
        root.setContentsMargins(16, 16, 16, 14)
        root.setSpacing(8)

        body_scroll = QScrollArea()
        body_scroll.setWidgetResizable(True)
        body_scroll.setFrameShape(QFrame.Shape.NoFrame)
        body_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body_scroll.setStyleSheet("QScrollArea{background:transparent; border:none;}")

        body = QWidget()
        body.setStyleSheet("background:transparent;")
        col = QVBoxLayout(body)
        col.setContentsMargins(2, 2, 6, 2)
        col.setSpacing(8)

        eyebrow = QLabel("BOOST PANEL")
        eyebrow.setObjectName("HudEyebrow")
        col.addWidget(eyebrow)

        header = QHBoxLayout()
        header.setSpacing(12)
        self.hero_cover = QLabel()
        self.hero_cover.setFixedSize(64, 80)
        self.hero_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hero_cover.setText("ICON")
        self.hero_cover.setStyleSheet(
            f"color:{THEME['muted_dim']}; background:{THEME['panel_alt']}; "
            f"border:1px solid {THEME['border']}; border-radius:12px; font-weight:700;"
        )
        header.addWidget(self.hero_cover, 0, Qt.AlignmentFlag.AlignTop)

        title_col = QVBoxLayout()
        title_col.setSpacing(3)
        self.boost_title = QLabel("尚未選擇遊戲")
        self.boost_title.setObjectName("HeroTitle")
        self.boost_title.setWordWrap(True)
        self.boost_title.setStyleSheet("font-size:18px; font-weight:700;")
        self.boost_subtitle = QLabel("從左側遊戲庫挑選一款開始")
        self.boost_subtitle.setObjectName("Muted")
        self.boost_subtitle.setWordWrap(True)
        self.boost_subtitle.setStyleSheet(f"color:{THEME['muted']}; font-size:11px;")
        self.detect_label = QLabel("程序：未選擇")
        self.detect_label.setStyleSheet(
            f"color:{THEME['muted_dim']}; font-size:11px; font-weight:600;"
        )
        title_col.addWidget(self.boost_title)
        title_col.addWidget(self.boost_subtitle)
        title_col.addWidget(self.detect_label)
        title_col.addStretch(1)
        header.addLayout(title_col, 1)
        col.addLayout(header)

        self.profile_label = QLabel("加速方案：—")
        self.profile_label.setWordWrap(True)
        self.profile_label.setStyleSheet(
            f"color:{THEME['accent']}; font-size:12px; font-weight:700;"
        )
        self.profile_detail = QLabel("選擇遊戲後顯示本機加速方案")
        self.profile_detail.setObjectName("Muted")
        self.profile_detail.setWordWrap(True)
        self.profile_detail.setStyleSheet(f"color:{THEME['muted']}; font-size:11px;")
        col.addWidget(self.profile_label)
        col.addWidget(self.profile_detail)

        self.status_chip = QLabel("待機中")
        self.status_chip.setObjectName("StatusChip")
        self.status_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_status_style(THEME["muted"], THEME["panel_alt"])
        col.addWidget(self.status_chip)

        self.speed_gauge = SpeedGauge()
        self.speed_gauge.setFixedSize(168, 168)
        col.addWidget(self.speed_gauge, 0, Qt.AlignmentFlag.AlignHCenter)

        latency_frame = QFrame()
        latency_frame.setStyleSheet(
            f"QFrame{{background:{THEME['panel_alt']}; border:1px solid {THEME['border']};"
            "border-radius:12px;}}"
        )
        latency_row = QHBoxLayout(latency_frame)
        latency_row.setContentsMargins(12, 8, 12, 8)
        latency_row.setSpacing(8)

        ping_col = QVBoxLayout()
        ping_col.setSpacing(1)
        ping_cap = QLabel("延遲")
        ping_cap.setStyleSheet(
            f"color:{THEME['muted_dim']}; font-size:10px; font-weight:700; border:none; background:transparent;"
        )
        self.panel_ping_value = QLabel("—")
        self.panel_ping_value.setStyleSheet(
            f"color:{THEME['text']}; font-size:15px; font-weight:700; border:none; background:transparent;"
        )
        ping_col.addWidget(ping_cap)
        ping_col.addWidget(self.panel_ping_value)
        latency_row.addLayout(ping_col, 1)

        loss_col = QVBoxLayout()
        loss_col.setSpacing(1)
        loss_cap = QLabel("丟包")
        loss_cap.setStyleSheet(
            f"color:{THEME['muted_dim']}; font-size:10px; font-weight:700; border:none; background:transparent;"
        )
        self.panel_loss_value = QLabel("—")
        self.panel_loss_value.setStyleSheet(
            f"color:{THEME['text']}; font-size:15px; font-weight:700; border:none; background:transparent;"
        )
        loss_col.addWidget(loss_cap)
        loss_col.addWidget(self.panel_loss_value)
        latency_row.addLayout(loss_col, 1)
        col.addWidget(latency_frame)

        self.panel_ping_host = QLabel("節點尚未測速")
        self.panel_ping_host.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.panel_ping_host.setStyleSheet(
            f"color:{THEME['muted_dim']}; font-size:10px;"
        )
        col.addWidget(self.panel_ping_host)
        self.ping_detail = self.panel_ping_host

        compare_title = QLabel("加速前後對照")
        compare_title.setStyleSheet("font-size:12px; font-weight:700;")
        col.addWidget(compare_title)
        self.compare_label = QLabel("加速前後會顯示延遲／CPU／FPS 對照")
        self.compare_label.setWordWrap(True)
        self.compare_label.setStyleSheet(
            f"color:{THEME['muted']}; font-size:11px;"
            f"background:{THEME['panel_alt']}; border:1px solid {THEME['hud_line']};"
            "border-radius:2px; padding:10px;"
        )
        col.addWidget(self.compare_label)

        self.fps_status_label = QLabel(self._fps_status)
        self.fps_status_label.setWordWrap(True)
        self.fps_status_label.setStyleSheet(
            f"color:{THEME['cyan']}; font-size:10px; font-weight:600;"
        )
        col.addWidget(self.fps_status_label)

        self.admin_hint_label = QLabel("")
        self.admin_hint_label.setWordWrap(True)
        self.admin_hint_label.setStyleSheet(
            f"color:{THEME['warning']}; font-size:10px; font-weight:600;"
        )
        if not self._is_admin:
            self.admin_hint_label.setText(
                "目前非系統管理員：遊戲優先權／DNS 可能失敗。建議以系統管理員執行。"
            )
        col.addWidget(self.admin_hint_label)

        throttle_head = QHBoxLayout()
        throttle_title = QLabel("背景降載預覽")
        throttle_title.setStyleSheet("font-size:12px; font-weight:700;")
        throttle_head.addWidget(throttle_title)
        throttle_head.addStretch(1)
        self.refresh_throttle_btn = QPushButton("刷新")
        self.refresh_throttle_btn.setObjectName("GhostButton")
        self.refresh_throttle_btn.setFixedHeight(26)
        self.refresh_throttle_btn.setEnabled(False)
        self.refresh_throttle_btn.clicked.connect(self._refresh_throttle)
        throttle_head.addWidget(self.refresh_throttle_btn)
        col.addLayout(throttle_head)

        hint = QLabel("勾選＝將降優先；取消勾選＝排除")
        hint.setStyleSheet(f"color:{THEME['muted_dim']}; font-size:10px;")
        col.addWidget(hint)

        self.pause_apps_check = QCheckBox("加速時暫停瀏覽器／雲端同步（停止後立即喚醒）")
        self.pause_apps_check.setChecked(self._prefs.pause_apps_for())
        self.pause_apps_check.setStyleSheet(
            f"color:{THEME['text']}; font-size:11px; spacing:8px;"
        )
        self.pause_apps_check.toggled.connect(self._on_pause_toggled)
        col.addWidget(self.pause_apps_check)
        self.request_pause_enabled.emit(self.pause_apps_check.isChecked())

        self.throttle_list = QListWidget()
        self.throttle_list.setMinimumHeight(96)
        self.throttle_list.setMaximumHeight(132)
        self.throttle_list.setStyleSheet(
            f"QListWidget{{background:{THEME['panel_alt']}; border:1px solid {THEME['border']};"
            f"border-radius:12px; padding:4px; color:{THEME['text']};}}"
            f"QListWidget::item{{padding:4px 6px;}}"
        )
        self.throttle_list.itemChanged.connect(self._on_throttle_item_changed)
        col.addWidget(self.throttle_list)

        self.steps_title = QLabel("執行紀錄")
        self.steps_title.setStyleSheet("font-size:12px; font-weight:700;")
        col.addWidget(self.steps_title)

        self.steps_label = QLabel("尚未套用")
        self.steps_label.setWordWrap(True)
        self.steps_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.steps_label.setMinimumHeight(64)
        self.steps_label.setStyleSheet(
            f"color:{THEME['muted']}; font-size:11px;"
            f"background:{THEME['panel_alt']}; border:1px solid {THEME['border']};"
            "border-radius:12px; padding:10px;"
        )
        col.addWidget(self.steps_label)
        col.addStretch(1)

        body_scroll.setWidget(body)
        root.addWidget(body_scroll, 1)

        self.boost_btn = QPushButton("BOOST")
        self.boost_btn.setObjectName("PrimaryButton")
        self.boost_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.boost_btn.setEnabled(False)
        self.boost_btn.clicked.connect(self._start_boost)
        root.addWidget(self.boost_btn)

        self.stop_btn = QPushButton("停止加速")
        self.stop_btn.setObjectName("GhostButton")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_boost)
        root.addWidget(self.stop_btn)

        self.refresh_ping_btn = QPushButton("重新測速")
        self.refresh_ping_btn.setObjectName("GhostButton")
        self.refresh_ping_btn.setEnabled(False)
        self.refresh_ping_btn.clicked.connect(self._refresh_ping)
        root.addWidget(self.refresh_ping_btn)
        return panel

    def _build_monitor_page(self) -> QWidget:
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(14)

        title = QLabel("系統效能監測")
        title.setObjectName("SectionTitle")
        col.addWidget(title)

        self.monitor_detail = QLabel("正在讀取系統狀態…")
        self.monitor_detail.setObjectName("Muted")
        col.addWidget(self.monitor_detail)

        panel = QFrame()
        panel.setObjectName("ProcessPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 18, 18, 18)

        heading = QLabel("佔用資源較高的背景程序")
        heading.setStyleSheet("font-weight:700; font-size:15px;")
        panel_layout.addWidget(heading)

        self.process_table = QTableWidget(0, 4)
        self.process_table.setHorizontalHeaderLabels(["程序", "PID", "CPU %", "記憶體 MB"])
        self.process_table.horizontalHeader().setStretchLastSection(True)
        self.process_table.verticalHeader().setVisible(False)
        self.process_table.setShowGrid(False)
        self.process_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.process_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        panel_layout.addWidget(self.process_table)
        col.addWidget(panel, 1)
        return page

    def _clear_game_rows(self) -> None:
        while self.game_rows.count():
            item = self.game_rows.takeAt(0)
            row_widget = item.widget()
            if row_widget is None:
                continue
            row_layout = row_widget.layout()
            if row_layout is not None:
                while row_layout.count():
                    child = row_layout.takeAt(0)
                    child_widget = child.widget()
                    if child_widget is not None:
                        child_widget.setParent(self._card_park)
            row_widget.deleteLater()

    def _build_game_cards(self, games: list[Game]) -> None:
        """Create cards once. Search only reflows row layouts afterwards."""
        self._clear_game_rows()
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()

        for game in games:
            card = GameCard(game)
            card.clicked.connect(self._select_game)
            if self.selected_game and self.selected_game.id == game.id:
                card.set_selected(True)
            card.setParent(self._card_park)
            self._cards.append(card)

    def _relayout_cards(self, games: list[Game]) -> None:
        """Pack visible cards into fresh rows — no absolute geometry, no ghosts."""
        visible_ids = {game.id for game in games}
        columns = 4

        self._clear_game_rows()

        visible_cards = [card for card in self._cards if card.game.id in visible_ids]
        hidden_cards = [card for card in self._cards if card.game.id not in visible_ids]

        for card in hidden_cards:
            card.setParent(self._card_park)
            card.hide()

        current_row: QHBoxLayout | None = None
        for index, card in enumerate(visible_cards):
            if index % columns == 0:
                row_widget = QWidget()
                row_widget.setStyleSheet(f"background:{THEME['bg']};")
                current_row = QHBoxLayout(row_widget)
                current_row.setContentsMargins(0, 0, 0, 0)
                current_row.setSpacing(14)
                current_row.setAlignment(Qt.AlignmentFlag.AlignLeft)
                self.game_rows.addWidget(row_widget)
            assert current_row is not None
            card.show()
            current_row.addWidget(card)

        self.game_rows.addStretch(1)
        self.game_scroll.verticalScrollBar().setValue(0)

        total = len(self._cards)
        shown = len(visible_cards)
        if not self.search.text().strip():
            self.search_status.setText(f"共 {total} 款遊戲")
        elif shown == 0:
            self.search_status.setText("找不到符合的遊戲，試試英文名或類型（如 FPS）")
        else:
            self.search_status.setText(f"找到 {shown} 款／共 {total} 款")

    def _on_search_text(self, _text: str) -> None:
        # Debounce: typing shouldn't rebuild/relayout on every IME keystroke.
        self._search_timer.start()

    def _apply_search(self) -> None:
        self._search_timer.stop()
        self._relayout_cards(self.catalog.search(self.search.text()))

    def _set_status_style(self, color: str, background: str) -> None:
        self.status_chip.setStyleSheet(
            f"QLabel#StatusChip{{background:{background}; color:{color}; "
            f"border-radius:12px; padding:10px 12px; font-weight:700;}}"
        )

    def _select_game(self, game: Game) -> None:
        switching = (
            self.selected_game is not None and self.selected_game.id != game.id
        )
        session_live = (
            self._boosted
            or self._boost_armed
            or self._boost_inflight
            or self._stop_requested
            or self._maintain_timer.isActive()
        )
        # Switching games while boosting used to clear UI flags without restore,
        # leaving maintain running and stop disabled — looks like stop is broken.
        if switching and session_live:
            self._stop_boost()

        same_session = (
            self.selected_game is not None
            and self.selected_game.id == game.id
            and session_live
            and not switching
        )

        self.selected_game = game
        for card in self._cards:
            card.set_selected(card.game.id == game.id)

        profile = profile_for(game)
        self._arm_timer.setInterval(profile.watch_interval_ms)

        self.boost_title.setText(game.name)
        self.boost_subtitle.setText(f"{game.genre}  ·  {game.ping_host}")
        self.profile_label.setText(f"加速方案：{profile.title}")
        self.profile_detail.setText(profile.summary)
        cover = load_cover(game.id, 64, 80)
        if cover is not None:
            self.hero_cover.setText("")
            self.hero_cover.setPixmap(cover)
            self.hero_cover.setStyleSheet(
                f"border:1px solid {THEME['border']}; border-radius:12px;"
            )

        pause_on = self._prefs.pause_apps_for(game.id)
        self.pause_apps_check.blockSignals(True)
        self.pause_apps_check.setChecked(pause_on)
        self.pause_apps_check.blockSignals(False)
        self.request_pause_enabled.emit(pause_on)
        self.refresh_ping_btn.setEnabled(True)
        self.refresh_throttle_btn.setEnabled(True)

        if same_session:
            self._set_latency_pending(game.ping_host)
            self.request_ping.emit(game)
            self.request_throttle.emit(game)
            if not self._throttle_timer.isActive():
                self._throttle_timer.start()
            return

        if session_live and not switching:
            # Still stopping / boosting this game — don't wipe chrome.
            self._set_latency_pending(game.ping_host)
            self.request_ping.emit(game)
            self.request_throttle.emit(game)
            if not self._throttle_timer.isActive():
                self._throttle_timer.start()
            return

        self._boosted = False
        self._boost_armed = False
        self._boost_inflight = False
        self._stop_requested = False
        self._stop_queued = False
        self._expecting_boost = False
        self._arm_timer.stop()
        self.detect_label.setText("程序：偵測中…")
        self.boost_btn.setEnabled(True)
        self.boost_btn.setText("BOOST")
        self.stop_btn.setEnabled(False)
        status = "已選擇 · 準備加速"
        if not self._is_admin:
            status = "已選擇 · 建議以系統管理員執行"
        self.status_chip.setText(status)
        self._set_status_style(THEME["text"], "#15213A")
        self.steps_title.setText("執行紀錄")
        self.steps_label.setText("將套用：" + "、".join(profile.focus))
        self._set_latency_pending(game.ping_host)
        self.request_ping.emit(game)
        self.request_throttle.emit(game)
        if not self._throttle_timer.isActive():
            self._throttle_timer.start()

    def _on_pause_toggled(self, checked: bool) -> None:
        self.request_pause_enabled.emit(checked)
        gid = self.selected_game.id if self.selected_game else None
        self._prefs.set_pause_apps(checked, game_id=gid)

    def _current_exclude_pids(self) -> tuple[int, ...]:
        excluded: list[int] = []
        for i in range(self.throttle_list.count()):
            item = self.throttle_list.item(i)
            if item is None:
                continue
            if item.checkState() != Qt.CheckState.Checked:
                pid = item.data(Qt.ItemDataRole.UserRole)
                if pid is not None:
                    excluded.append(int(pid))
        return tuple(excluded)

    def _current_exclude_names(self) -> set[str]:
        names: set[str] = set()
        for i in range(self.throttle_list.count()):
            item = self.throttle_list.item(i)
            if item is None:
                continue
            if item.checkState() != Qt.CheckState.Checked:
                name = item.data(Qt.ItemDataRole.UserRole + 1)
                if name:
                    names.add(str(name).lower())
        return names

    def _persist_excludes(self) -> None:
        if not self.selected_game:
            return
        self._prefs.set_exclude_names(
            self.selected_game.id, self._current_exclude_names()
        )

    def _on_throttle_item_changed(self, item: QListWidgetItem) -> None:
        del item
        self._persist_excludes()

    def _refresh_throttle(self) -> None:
        if self.selected_game is None:
            return
        if self._boosted:
            return
        self.request_throttle.emit(self.selected_game)

    def _snapshot_compare_before(self) -> None:
        self._compare_live = True
        self._compare = SessionCompare(
            ping_ms=MetricPair("延遲", self._last_ping_ms, None, "ms", True),
            cpu_percent=MetricPair("CPU", self._last_cpu if self._last_cpu else None, None, "%", True),
            fps=MetricPair("FPS", self._last_fps, None, "FPS", False),
            note="加速生效後會填入「後」欄並持續更新",
        )
        self._render_compare()

    def _seed_compare_after(self) -> None:
        """Fill after-column immediately when boost becomes active."""
        if not self._compare_live:
            return
        # Backfill before if the pre-boost ping arrived late.
        if self._compare.ping_ms.before is None and self._last_ping_ms is not None:
            self._compare.ping_ms.before = self._last_ping_ms
        if self._compare.cpu_percent.before is None and self._last_cpu:
            self._compare.cpu_percent.before = self._last_cpu
        if self._compare.fps.before is None and self._last_fps is not None:
            self._compare.fps.before = self._last_fps

        if self._last_ping_ms is not None:
            self._compare.ping_ms.after = self._last_ping_ms
        if self._last_cpu:
            self._compare.cpu_percent.after = self._last_cpu
        if self._last_fps is not None:
            self._compare.fps.after = self._last_fps
        self._compare.note = "「後」欄持續更新中（延遲會再測一次）"
        self._render_compare()

    def _update_compare_after(
        self,
        *,
        ping_ms: float | None = None,
        cpu: float | None = None,
        fps: float | None = None,
    ) -> None:
        if not self._compare_live:
            return
        if not (self._boosted or self._boost_armed):
            return
        if ping_ms is not None:
            self._compare.ping_ms.after = ping_ms
        if cpu is not None:
            self._compare.cpu_percent.after = cpu
        if fps is not None:
            self._compare.fps.after = fps
        if self._compare.note.startswith("「後」"):
            self._compare.note = "「後」欄持續更新中"
        self._render_compare()

    def _render_compare(self) -> None:
        c = self._compare
        lines = [
            f"延遲   前 {c.ping_ms.before_text}  →  後 {c.ping_ms.after_text}  （{c.ping_ms.delta_text}）",
            f"CPU    前 {c.cpu_percent.before_text}  →  後 {c.cpu_percent.after_text}  （{c.cpu_percent.delta_text}）",
            f"FPS    前 {c.fps.before_text}  →  後 {c.fps.after_text}  （{c.fps.delta_text}）",
        ]
        if c.note:
            lines.append(c.note)
        self.compare_label.setText("\n".join(lines))
        if hasattr(self, "fps_status_label"):
            self.fps_status_label.setText(self._fps_status)

    def _start_boost(self) -> None:
        if not self.selected_game:
            return
        if self._boost_inflight:
            return
        if self._stop_requested:
            return
        self._worker.clear_stop()
        self._stop_requested = False
        self._stop_queued = False
        self._expecting_boost = True
        self._boost_inflight = True
        self._stop_watchdog.stop()
        self._snapshot_compare_before()
        self.boost_btn.setEnabled(False)
        # Allow cancel while applying — previously stop was disabled here.
        self.stop_btn.setEnabled(True)
        self.boost_btn.setText("加速中…")
        self.status_chip.setText("正在套用本機優化…")
        self.steps_title.setText("執行紀錄")
        self.steps_label.setText("套用中…")
        self._set_latency_pending(self.selected_game.ping_host)
        self.request_ping.emit(self.selected_game)
        self.request_boost.emit(self.selected_game, self._current_exclude_pids())

    def _stop_boost(self) -> None:
        # Clear armed state immediately so retry timer cannot re-queue boost
        # ahead of / behind this stop request.
        self._stop_requested = True
        self._expecting_boost = False
        self._boost_armed = False
        self._boosted = False
        self._arm_timer.stop()
        self._maintain_timer.stop()
        # Mark cancel on worker immediately (before queued stop slot runs),
        # so an in-flight boost_game/maintain cannot finish as SUCCESS.
        self._worker.mark_stop()
        self.boost_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.status_chip.setText("正在停止加速…")
        self.steps_title.setText("還原檢查表")
        self.steps_label.setText("正在喚醒暫停程式，接著還原優先權…")
        self._queue_stop_boost()
        if not self._stop_watchdog.isActive():
            self._stop_watchdog.start()

    def _queue_stop_boost(self) -> None:
        if self._stop_queued:
            return
        self._stop_queued = True
        self.request_stop_boost.emit()

    def _force_stop_ui(self) -> None:
        """If worker never returns STOPPED, unstick the panel."""
        if not self._stop_requested:
            return
        self._apply_stopped_ui(
            message="加速已停止（還原逾時，狀態已重置）。"
        )

    def _apply_stopped_ui(self, message: str | None = None) -> None:
        self._stop_watchdog.stop()
        self._stop_requested = False
        self._stop_queued = False
        self._expecting_boost = False
        self._boosted = False
        self._boost_armed = False
        self._boost_inflight = False
        self._compare_live = False
        try:
            self._worker.clear_stop()
        except Exception:
            pass
        self._arm_timer.stop()
        self._maintain_timer.stop()
        self.boost_btn.setText("BOOST")
        self.boost_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_chip.setText("加速已停止")
        self._set_status_style(THEME["muted"], THEME["panel_alt"])
        self.detect_label.setText("程序：已還原")
        self.detect_label.setStyleSheet(
            f"color:{THEME['muted_dim']}; font-size:11px; font-weight:600;"
        )
        if message:
            self.steps_title.setText("還原檢查表")
            self.steps_label.setText(message)
        self._compare.note = "本次加速已結束（保留最後對照）"
        self._render_compare()
        self._refresh_throttle()

    def _retry_armed_boost(self) -> None:
        if self._stop_requested or not self._expecting_boost:
            return
        if not self._boost_armed or self._boosted or not self.selected_game:
            return
        if self._boost_inflight:
            return
        self._boost_inflight = True
        self.request_boost.emit(self.selected_game, self._current_exclude_pids())

    def _render_steps(self, steps: tuple[str, ...]) -> None:
        self.steps_title.setText("執行紀錄")
        if not steps:
            self.steps_label.setText("尚無加速動作")
            return
        self.steps_label.setText("\n".join(f"• {step}" for step in steps))

    def _render_restore(self, result: BoostResult) -> None:
        self.steps_title.setText("還原檢查表")
        items = result.restore_items
        if not items:
            self.steps_label.setText(result.message or "已停止")
            return
        lines = [result.message] if result.message else []
        for item in items:
            mark = "✓" if item.ok else "✗"
            lines.append(f"{mark}  {item.label}")
        self.steps_label.setText("\n".join(lines))

    def _on_throttle(self, rows: list[ThrottleCandidate]) -> None:
        session_unchecked = set(self._current_exclude_pids())
        remembered: set[str] = set()
        if self.selected_game:
            remembered = self._prefs.exclude_names_for(self.selected_game.id)

        self.throttle_list.blockSignals(True)
        self.throttle_list.clear()
        if not rows:
            empty = QListWidgetItem("目前沒有明顯高負載背景程序")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.throttle_list.addItem(empty)
            self.throttle_list.blockSignals(False)
            return
        for row in rows:
            item = QListWidgetItem(
                f"{row.name}    {row.cpu_percent:.0f}% · {row.memory_mb:.0f} MB"
            )
            item.setData(Qt.ItemDataRole.UserRole, row.pid)
            item.setData(Qt.ItemDataRole.UserRole + 1, row.name)
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
            )
            excluded = (
                row.pid in session_unchecked
                or row.name.lower() in remembered
            )
            item.setCheckState(
                Qt.CheckState.Unchecked if excluded else Qt.CheckState.Checked
            )
            self.throttle_list.addItem(item)
        self.throttle_list.blockSignals(False)

    def _set_latency_pending(self, host: str) -> None:
        self._ping_busy = True
        self.panel_ping_value.setText("…")
        self.panel_loss_value.setText("…")
        self.panel_ping_host.setText(f"測速中 · {host}")
        self.refresh_ping_btn.setEnabled(False)

    def _refresh_ping(self) -> None:
        if not self.selected_game:
            QMessageBox.information(self, "PingVault", "請先選擇一款遊戲。")
            return
        if self._ping_busy:
            return
        self._set_latency_pending(self.selected_game.ping_host)
        self.request_ping.emit(self.selected_game)

    def _tone(self, value: int) -> str:
        if value >= 85:
            return THEME["danger"]
        if value >= 65:
            return THEME["warning"]
        return THEME["accent"]

    def _temp_tone(self, celsius: float) -> str:
        if celsius >= 85:
            return THEME["danger"]
        if celsius >= 75:
            return THEME["warning"]
        return THEME["success"]

    def _on_fps(self, sample: FpsSample) -> None:
        if sample.fps is not None:
            self._last_fps = float(sample.fps)
            self._fps_status = (
                f"FPS：RTSS 已連線 · {sample.fps:.0f} FPS"
                + (f" · {sample.detail}" if sample.detail else "")
            )
            if self._compare_live and not (self._boosted or self._boost_armed):
                if self._compare.fps.before is None:
                    self._compare.fps.before = self._last_fps
                    self._render_compare()
            self._update_compare_after(fps=self._last_fps)
        elif sample.source == "rtss":
            self._fps_status = f"FPS：RTSS 已連線，等待遊戲畫面（{sample.detail or '尚無數據'}）"
        else:
            self._fps_status = (
                "FPS：未偵測到 RTSS。請安裝並開啟 RivaTuner Statistics Server，"
                "進遊戲後這裡才會顯示幀數。"
            )
        if hasattr(self, "fps_status_label"):
            color = THEME["cyan"] if sample.source == "rtss" or sample.fps else THEME["muted_dim"]
            self.fps_status_label.setStyleSheet(
                f"color:{color}; font-size:10px; font-weight:600;"
            )
            self.fps_status_label.setText(self._fps_status)

    def _on_recovery(self, notes: object) -> None:
        rows = notes if isinstance(notes, (list, tuple)) else ()
        if not rows:
            return
        self.steps_title.setText("啟動還原")
        self.steps_label.setText(
            "偵測到上次異常中斷，已嘗試還原：\n"
            + "\n".join(f"• {n}" for n in rows)
        )
        self.status_chip.setText("已從上次強制關閉／崩潰還原")
        self._set_status_style(THEME["warning"], "#2A220E")

    def _on_maintain(self, result: BoostResult) -> None:
        if self._stop_requested:
            return
        if result.status == BoostStatus.WAITING:
            self.detect_label.setText("程序：尚未偵測到（持續監測）")
            return
        if result.detected_processes:
            self.detect_label.setText(
                "程序：" + "、".join(result.detected_processes[:3])
            )
            self.detect_label.setStyleSheet(
                f"color:{THEME['success']}; font-size:11px; font-weight:600;"
            )
        if result.maintain_notes:
            # Keep full applied steps; append live maintain line.
            base = list(result.applied_steps) if result.applied_steps else []
            live = "持續：" + "、".join(result.maintain_notes[:3])
            self.steps_title.setText("執行紀錄")
            self.steps_label.setText(
                "\n".join(f"• {s}" for s in base[-6:]) + f"\n• {live}"
            )

    def _on_stats(self, stats: SystemStats) -> None:
        self._last_cpu_percent = int(stats.cpu_percent)
        self._last_cpu = float(stats.cpu_percent)
        if self._compare_live and not (self._boosted or self._boost_armed):
            if self._compare.cpu_percent.before is None and self._last_cpu:
                self._compare.cpu_percent.before = self._last_cpu
                self._render_compare()
        self._update_compare_after(cpu=self._last_cpu)
        # Keep any existing CPU temp subline if thermal already arrived.
        current_sub = self.cpu_chip._sub.text()  # noqa: SLF001
        self.cpu_chip.set_value(
            f"{stats.cpu_percent:.0f}%",
            int(stats.cpu_percent),
            self._tone(int(stats.cpu_percent)),
            sub=current_sub or None,
        )
        self.mem_chip.set_value(
            f"{stats.memory_percent:.0f}%",
            int(stats.memory_percent),
            self._tone(int(stats.memory_percent)),
        )
        self.disk_chip.set_value(
            f"{stats.disk_percent:.0f}%",
            int(stats.disk_percent),
            self._tone(int(stats.disk_percent)),
        )
        self.monitor_detail.setText(
            f"CPU {stats.cpu_percent:.1f}%　｜　"
            f"記憶體 {stats.memory_used_gb:.1f}/{stats.memory_total_gb:.1f} GB "
            f"({stats.memory_percent:.0f}%)　｜　"
            f"磁碟 {stats.disk_used_gb:.0f}/{stats.disk_total_gb:.0f} GB "
            f"({stats.disk_percent:.0f}%)"
        )

    def _on_thermal(self, thermal: ThermalStats) -> None:
        if thermal.cpu_c is not None:
            self.cpu_chip.set_value(
                f"{self._last_cpu_percent}%",
                self._last_cpu_percent,
                self._tone(self._last_cpu_percent),
                sub=f"{thermal.cpu_c:.0f}°C",
            )
        else:
            self.cpu_chip.set_value(
                f"{self._last_cpu_percent}%",
                self._last_cpu_percent,
                self._tone(self._last_cpu_percent),
                sub="溫度 --",
            )

        if thermal.gpu_c is not None:
            # Map 40–95°C into bar fill for quick glance.
            bar = int(max(0, min(100, (thermal.gpu_c - 30) * (100 / 70))))
            name = thermal.gpu_name or "GPU"
            short = name if len(name) <= 18 else name[:16] + "…"
            self.gpu_chip.set_value(
                f"{thermal.gpu_c:.0f}°C",
                bar,
                self._temp_tone(thermal.gpu_c),
                sub=short,
            )
        else:
            self.gpu_chip.set_value("--", 0, THEME["muted_dim"], sub="未偵測到 GPU 感測")

    def _on_processes(self, rows: list[ProcessInfo]) -> None:
        self.process_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            self.process_table.setItem(i, 0, QTableWidgetItem(row.name))
            self.process_table.setItem(i, 1, QTableWidgetItem(str(row.pid)))
            self.process_table.setItem(i, 2, QTableWidgetItem(f"{row.cpu_percent:.1f}"))
            self.process_table.setItem(i, 3, QTableWidgetItem(f"{row.memory_mb:.0f}"))

    def _poll_speed(self) -> None:
        self._on_speed(self._net_speed.sample())

    def _on_speed(self, speed: NetSpeedStats) -> None:
        self.speed_gauge.set_speed(
            speed.down_bps,
            speed.up_bps,
            speed.down_text,
            speed.up_text,
        )

    def _on_ping(self, result: PingResult) -> None:
        self._ping_busy = False
        self.refresh_ping_btn.setEnabled(self.selected_game is not None)

        if result.ok and result.avg_ms is not None:
            avg = result.avg_ms
            self._last_ping_ms = float(avg)
            # Ping started with BOOST often returns before SUCCESS flags flip —
            # backfill「前」if still empty; write「後」once session is live.
            if self._compare_live and not (self._boosted or self._boost_armed):
                if self._compare.ping_ms.before is None:
                    self._compare.ping_ms.before = self._last_ping_ms
                    self._render_compare()
            self._update_compare_after(ping_ms=self._last_ping_ms)
            loss = result.packet_loss_percent
            tone = self._tone(int(avg))
            self.ping_chip.set_value(f"{avg:.0f} ms", min(100, int(avg)), tone)
            self.loss_chip.set_value(f"{loss:.0f}%", int(loss), self._tone(int(loss)))
            self.panel_ping_value.setText(f"{avg:.0f} ms")
            self.panel_ping_value.setStyleSheet(
                f"color:{tone}; font-size:16px; font-weight:700; border:none; background:transparent;"
            )
            self.panel_loss_value.setText(f"{loss:.0f}%")
            self.panel_ping_host.setText(
                f"min {result.min_ms:.0f} / max {result.max_ms:.0f} ms  ·  {result.host}"
            )
            # Don't override boost status chip while accelerating.
            if not self._boosted and not self._boost_armed:
                color = THEME["success"] if avg < 80 else THEME["warning"] if avg < 150 else THEME["danger"]
                self.status_chip.setText(f"延遲 {avg:.0f} ms")
                self._set_status_style(color, "#15213A")
        else:
            self.ping_chip.set_value("失敗", 100, THEME["danger"])
            self.loss_chip.set_value("100%", 100, THEME["danger"])
            self.panel_ping_value.setText("失敗")
            self.panel_ping_value.setStyleSheet(
                f"color:{THEME['danger']}; font-size:16px; font-weight:700; border:none; background:transparent;"
            )
            self.panel_loss_value.setText("—")
            self.panel_ping_host.setText(
                f"{result.host}  ·  {result.message or '請檢查網路連線'}"
            )
            detail = f"延遲測速失敗 · {result.host}　｜　{result.message or '請檢查網路連線'}"
            if not self._boosted and not self._boost_armed:
                self.status_chip.setText("延遲測速失敗")
                self._set_status_style(THEME["danger"], "#15213A")

    def _on_boost(self, result: BoostResult) -> None:
        self._boost_inflight = False

        if result.status == BoostStatus.STOPPED:
            self._render_restore(result)
            self._apply_stopped_ui()
            return

        # User already hit stop, or this result belongs to a cancelled session.
        if self._stop_requested or not self._expecting_boost:
            if self._stop_requested:
                self._worker.mark_stop()
                self._queue_stop_boost()
            return

        self.boost_btn.setEnabled(True)
        if result.detected_processes:
            self.detect_label.setText(
                "程序：" + "、".join(result.detected_processes[:3])
            )
            self.detect_label.setStyleSheet(
                f"color:{THEME['success']}; font-size:11px; font-weight:600;"
            )
        elif result.status == BoostStatus.WAITING:
            self.detect_label.setText("程序：尚未偵測到（待命中）")
            self.detect_label.setStyleSheet(
                f"color:{THEME['warning']}; font-size:11px; font-weight:600;"
            )

        self._render_steps(result.applied_steps)

        if result.status == BoostStatus.SUCCESS:
            self._boosted = True
            self._boost_armed = False
            self._arm_timer.stop()
            if not self._maintain_timer.isActive():
                self._maintain_timer.start()
            self.boost_btn.setText("加速中")
            self.stop_btn.setEnabled(True)
            self.status_chip.setText("Boost 已啟用 · 持續平衡中")
            self._set_status_style(THEME["success"], "#123024")
            self._seed_compare_after()
            # Fresh post-boost latency sample for the「後」column.
            if self.selected_game is not None:
                self._set_latency_pending(self.selected_game.ping_host)
                self.request_ping.emit(self.selected_game)
            return

        if result.status == BoostStatus.WAITING:
            self._boost_armed = True
            self._boosted = False
            if not self._arm_timer.isActive():
                self._arm_timer.start()
            if not self._maintain_timer.isActive():
                self._maintain_timer.start()
            self.boost_btn.setText("監測中")
            self.stop_btn.setEnabled(True)
            self.status_chip.setText("等待遊戲啟動中")
            self._set_status_style(THEME["warning"], "#2A220E")
            self._seed_compare_after()
            if self.selected_game is not None:
                self._set_latency_pending(self.selected_game.ping_host)
                self.request_ping.emit(self.selected_game)
            return

        self._stop_requested = False
        self._expecting_boost = False
        self._boost_armed = False
        self._arm_timer.stop()
        self._maintain_timer.stop()
        self.boost_btn.setText("BOOST")
        self.boost_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_chip.setText("需要管理員權限")
        self._set_status_style(THEME["danger"], "#15213A")
        if result.status == BoostStatus.DENIED or "優先權" in (result.message or ""):
            QMessageBox.warning(
                self,
                "PingVault · 需要系統管理員",
                f"{result.message}\n\n{ADMIN_HELP}",
            )
        else:
            QMessageBox.warning(self, "PingVault", result.message)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        # Close to tray unless user chose Quit from tray menu.
        if getattr(self, "tray", None) is not None and not self._force_quit:
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "PingVault",
                "已縮小到系統匣，加速／監測仍在背景運作。",
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )
            return

        # Real quit (tray「結束並還原」、系統登出、約 to quit)：一定先停加速。
        self.shutdown_restore()

        self._stats_timer.stop()
        self._speed_timer.stop()
        self._proc_timer.stop()
        self._throttle_timer.stop()
        self._arm_timer.stop()
        self._maintain_timer.stop()
        self._search_timer.stop()
        if getattr(self, "tray", None) is not None:
            self.tray.hide()
        for thread, worker in (
            (self._worker_thread, self._worker),
            (self._ping_thread, self._ping_worker),
        ):
            thread.quit()
            if not thread.wait(3000):
                thread.terminate()
                thread.wait(1000)
            worker.deleteLater()
            thread.deleteLater()
        super().closeEvent(event)
