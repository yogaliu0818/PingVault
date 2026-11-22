from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from pingvault.services.app_pause import AppPauseManager
from pingvault.services.fps import FpsMonitor, FpsSample
from pingvault.services.games import Game
from pingvault.services.network import NetworkMonitor, PingResult
from pingvault.services.optimizer import (
    BoostResult,
    BoostStatus,
    Optimizer,
    ProcessInfo,
    RestoreItem,
    ThrottleCandidate,
)
from pingvault.services.performance import PerformanceMonitor, SystemStats
from pingvault.services.profiles import profile_for
from pingvault.services.thermal import ThermalMonitor, ThermalStats


class MonitorWorker(QObject):
    """System stats, thermals, process list, throttle preview, boost, maintain."""

    stats_ready = Signal(object)
    thermal_ready = Signal(object)
    processes_ready = Signal(object)
    throttle_ready = Signal(object)
    boost_ready = Signal(object)
    maintain_ready = Signal(object)
    fps_ready = Signal(object)
    recovery_ready = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._perf = PerformanceMonitor()
        self._thermal = ThermalMonitor()
        self._opt = Optimizer()
        self._pause = AppPauseManager()
        self._fps = FpsMonitor()
        self._pause_enabled = True

        # Ledgers may already be cleared by main.session_restore; still merge
        # any notes captured during Optimizer/AppPauseManager construction.
        notes = list(getattr(self._opt, "startup_recovery_notes", ()) or ())
        pause_recovery = getattr(self._pause, "startup_resume", None)
        if pause_recovery is not None:
            notes.append(pause_recovery.message)
            notes.extend(f"恢復 {n}" for n in pause_recovery.resumed[:6])
        self._recovery_notes = tuple(notes)

    @Slot()
    def emit_recovery(self) -> None:
        if self._recovery_notes:
            self.recovery_ready.emit(self._recovery_notes)

    @Slot()
    def sample_stats(self) -> None:
        stats: SystemStats = self._perf.sample()
        self.stats_ready.emit(stats)
        thermal: ThermalStats = self._thermal.sample()
        self.thermal_ready.emit(thermal)
        fps: FpsSample = self._fps.sample()
        self.fps_ready.emit(fps)

    @Slot()
    def sample_processes(self) -> None:
        rows: list[ProcessInfo] = self._opt.list_top_processes()
        self.processes_ready.emit(rows)

    @Slot(object)
    def sample_throttle(self, game: object) -> None:
        g = game if isinstance(game, Game) else None
        rows: list[ThrottleCandidate] = self._opt.list_throttle_candidates(g)
        self.throttle_ready.emit(rows)

    @Slot(bool)
    def set_pause_enabled(self, enabled: bool) -> None:
        self._pause_enabled = bool(enabled)

    def mark_stop(self) -> None:
        """Immediate cancel flag (callable from UI thread)."""
        self._opt.mark_stop()

    def clear_stop(self) -> None:
        self._opt.clear_stop()

    @Slot(object, object)
    def boost_game(self, game: Game, exclude_pids: object = ()) -> None:
        excludes = tuple(exclude_pids) if exclude_pids else ()
        try:
            result: BoostResult = self._opt.boost_game(game, exclude_pids=excludes)
        except Exception as exc:
            # Partial boost may have mutated priorities — always restore.
            self._opt.mark_stop()
            try:
                self.stop_boost()
            except Exception:
                self.boost_ready.emit(
                    BoostResult(
                        status=BoostStatus.STOPPED,
                        message=f"加速中斷：{exc}",
                        applied_steps=(),
                        restore_items=(RestoreItem("加速異常中止", False),),
                    )
                )
            return

        # User cancelled while boost was running — treat as stop.
        if result.status == BoostStatus.STOPPED or self._opt._aborted():  # noqa: SLF001
            self.stop_boost()
            return

        steps = list(result.applied_steps)

        if self._pause_enabled and result.status in (
            BoostStatus.SUCCESS,
            BoostStatus.WAITING,
        ):
            pause = self._pause.pause_running()
            steps.append(pause.message)
            for name in pause.paused[:8]:
                steps.append(f"暫停 {name}")
            result = BoostResult(
                status=result.status,
                message=f"{result.message} {pause.message}".strip(),
                profile=result.profile,
                affected_pids=result.affected_pids,
                applied_steps=tuple(steps),
                restore_items=result.restore_items,
                detected_processes=result.detected_processes,
                maintain_notes=result.maintain_notes,
            )

        # Cancel may have arrived during pause.
        if self._opt._aborted():  # noqa: SLF001
            self.stop_boost()
            return

        self.boost_ready.emit(result)

    @Slot()
    def maintain_boost(self) -> None:
        if self._opt._aborted():  # noqa: SLF001
            return
        result = self._opt.maintain_boost()
        if result is not None:
            self.maintain_ready.emit(result)

    @Slot()
    def stop_boost(self) -> None:
        self._opt.mark_stop()
        steps: list[str] = []
        restore_items: list[RestoreItem] = []

        # Wake suspended apps FIRST — do not wait for powercfg / priority restore.
        # Suspended processes get compressed/paged out; users feel this as lag.
        try:
            if self._pause.is_active or self._pause.path.exists():
                resume = self._pause.resume_all()
                steps.append(resume.message)
                restore_items.append(
                    RestoreItem(
                        f"暫停程式快速恢復（{len(resume.resumed)}）",
                        True,
                    )
                )
            else:
                self._pause.resume_all()
        except Exception as exc:
            steps.append(f"恢復暫停程式失敗：{exc}")
            restore_items.append(RestoreItem("暫停程式恢復", False))

        try:
            result: BoostResult = self._opt.stop_boost()
            steps.extend(result.applied_steps)
            restore_items.extend(result.restore_items)
            message = result.message
            profile = result.profile
        except Exception as exc:
            steps.append(f"還原時發生錯誤：{exc}")
            restore_items.append(RestoreItem("還原流程", False))
            message = "加速已停止（還原時有錯誤）。"
            profile = None

        self.boost_ready.emit(
            BoostResult(
                status=BoostStatus.STOPPED,
                message=message,
                profile=profile,
                applied_steps=tuple(steps),
                restore_items=tuple(restore_items),
            )
        )


class PingWorker(QObject):
    """ICMP latency on its own thread so boost never blocks ping (or vice versa)."""

    ping_ready = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._net = NetworkMonitor()

    @Slot(object)
    def ping_game(self, game: Game) -> None:
        profile = profile_for(game)
        count = min(4, profile.ping_count)
        result: PingResult = self._net.ping(
            game.ping_host,
            count=count,
            timeout_ms=profile.ping_timeout_ms,
        )
        self.ping_ready.emit(result)
