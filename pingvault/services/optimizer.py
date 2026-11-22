from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import psutil

from .games import Game
from .ledger import BoostLedger, LedgerEntry, LedgerStore
from .profiles import BoostProfile, profile_for
from .system_tune import SystemTune


class BoostStatus(str, Enum):
    SUCCESS = "success"
    WAITING = "waiting"
    DENIED = "denied"
    STOPPED = "stopped"


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    name: str
    cpu_percent: float
    memory_mb: float


@dataclass(frozen=True)
class ThrottleCandidate:
    pid: int
    name: str
    cpu_percent: float
    memory_mb: float


@dataclass(frozen=True)
class RestoreItem:
    label: str
    ok: bool


@dataclass(frozen=True)
class BoostResult:
    status: BoostStatus
    message: str
    profile: BoostProfile | None = None
    affected_pids: tuple[int, ...] = ()
    applied_steps: tuple[str, ...] = ()
    restore_items: tuple[RestoreItem, ...] = ()
    detected_processes: tuple[str, ...] = ()
    maintain_notes: tuple[str, ...] = ()

    @property
    def success(self) -> bool:
        return self.status == BoostStatus.SUCCESS


@dataclass
class _PriorityRestore:
    pid: int
    nice: int | float
    name: str = ""
    create_time: float = 0.0
    kind: str = "priority"


@dataclass
class _BgWatch:
    busy_hits: int = 0
    calm_hits: int = 0


# Never throttle these.
_PROTECTED_NAMES = {
    "system",
    "registry",
    "smss.exe",
    "csrss.exe",
    "wininit.exe",
    "winlogon.exe",
    "services.exe",
    "lsass.exe",
    "svchost.exe",
    "fontdrvhost.exe",
    "dwm.exe",
    "explorer.exe",
    "taskmgr.exe",
    "securityhealthservice.exe",
    "memory compression",
    "python.exe",
    "pythonw.exe",
    "audiodg.exe",
    "searchhost.exe",
    "shellexperiencehost.exe",
    "startmenuexperiencehost.exe",
    "textinputhost.exe",
    "gameoverlayui.exe",
    "gameoverlayui64.exe",
    # Voice / overlay / capture / GPU stacks
    "discord.exe",
    "discordptb.exe",
    "discordcanary.exe",
    "obs64.exe",
    "obs32.exe",
    "obs.exe",
    "streamlabs obs.exe",
    "nvcontainer.exe",
    "nvidia share.exe",
    "nvidia overlay.exe",
    "amdow.exe",
    "radeonsoftware.exe",
    "rtss.exe",
    "encoderserver.exe",
    "steam.exe",
}

_SKIP_PATH_NAMES = {
    "gameoverlayui.exe",
    "gameoverlayui64.exe",
    "steamwebhelper.exe",
    "steamservice.exe",
}


class Optimizer:
    """Genre boost profiles + crash-safe ledger + continuous background balance."""

    def __init__(self) -> None:
        self._tune = SystemTune()
        self._ledger = LedgerStore()
        self._active_game: Game | None = None
        self._active_game_id: str | None = None
        self._exclude_pids: set[int] = set()
        self._priority_restores: list[_PriorityRestore] = []
        self._throttled_restores: list[_PriorityRestore] = []
        self._bg_watch: dict[int, _BgWatch] = {}
        self._last_steps: list[str] = []
        self._dns_flushed = False
        self._power_changed = False
        # Set from UI thread; boost/maintain on worker thread must honor it.
        self._stop_requested = False
        self.startup_recovery_notes: list[str] = self.recover_from_ledger()

    @property
    def is_active(self) -> bool:
        return self._active_game_id is not None

    def mark_stop(self) -> None:
        """Thread-safe-enough cancel flag so in-flight boost cannot finish as SUCCESS."""
        self._stop_requested = True

    def clear_stop(self) -> None:
        self._stop_requested = False

    def _aborted(self) -> bool:
        return bool(self._stop_requested)

    def recover_from_ledger(self) -> list[str]:
        """On launch, restore any leftover priority changes from a crash."""
        data = self._ledger.load()
        if not data.active and not data.entries:
            return []
        notes = self._restore_ledger_entries(data)
        if data.timer_raised:
            self._tune._timer_active = True  # noqa: SLF001
            notes.append(self._tune.disable_high_timer_resolution())
        if data.previous_power_scheme:
            self._tune.state.previous_power_scheme = data.previous_power_scheme
            notes.append(self._tune.restore_power_scheme())
        self._ledger.clear()
        self._reset_session_state()
        return notes

    def _reset_session_state(self) -> None:
        self._active_game = None
        self._active_game_id = None
        self._exclude_pids.clear()
        self._priority_restores.clear()
        self._throttled_restores.clear()
        self._bg_watch.clear()
        self._dns_flushed = False
        self._power_changed = False

    def list_top_processes(self, limit: int = 8) -> list[ProcessInfo]:
        for proc in psutil.process_iter(["pid"]):
            try:
                proc.cpu_percent(interval=None)
            except (psutil.Error, ProcessLookupError, PermissionError):
                continue

        psutil.cpu_percent(interval=0.15)

        rows: list[ProcessInfo] = []
        for proc in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                info = proc.info
                mem = info.get("memory_info")
                memory_mb = (mem.rss / (1024 * 1024)) if mem else 0.0
                rows.append(
                    ProcessInfo(
                        pid=int(info["pid"]),
                        name=str(info.get("name") or "unknown"),
                        cpu_percent=float(proc.cpu_percent(interval=None) or 0.0),
                        memory_mb=memory_mb,
                    )
                )
            except (psutil.Error, ProcessLookupError, PermissionError):
                continue

        rows.sort(key=lambda p: (p.cpu_percent, p.memory_mb), reverse=True)
        return rows[:limit]

    def _path_hints(self, game: Game) -> set[str]:
        hints: set[str] = {game.id.lower()}
        compact = "".join(ch for ch in game.name.lower() if ch.isalnum())
        if len(compact) >= 4:
            hints.add(compact)
        for alias in game.aliases:
            a = "".join(ch for ch in alias.lower() if ch.isalnum())
            if len(a) >= 4:
                hints.add(a)
        for proc_name in game.process_names:
            stem = proc_name.lower().removesuffix(".exe")
            if len(stem) >= 3:
                hints.add(stem)
        return hints

    def find_game_processes(self, game: Game) -> list[psutil.Process]:
        targets = {name.lower() for name in game.process_names}
        stems = {name.lower().removesuffix(".exe") for name in game.process_names}
        hints = self._path_hints(game)
        found: dict[int, psutil.Process] = {}

        for proc in psutil.process_iter(["pid", "name", "exe"]):
            try:
                info = proc.info
                name = str(info.get("name") or "").lower()
                if not name or name in _SKIP_PATH_NAMES:
                    continue
                pid = int(info["pid"])

                if name in targets or name.removesuffix(".exe") in stems:
                    found[pid] = proc
                    continue

                exe = str(info.get("exe") or "").lower().replace("\\", "/")
                if not exe:
                    continue
                in_store = any(
                    key in exe
                    for key in (
                        "steamapps/common/",
                        "epic games/",
                        "riot games/",
                        "xboxgames/",
                        "/games/",
                    )
                )
                if not in_store:
                    continue
                for hint in hints:
                    if hint and hint in exe:
                        found[pid] = proc
                        break
            except (psutil.Error, ProcessLookupError, PermissionError):
                continue

        return list(found.values())

    def list_throttle_candidates(
        self, game: Game | None = None, limit: int = 8
    ) -> list[ThrottleCandidate]:
        game_pids: set[int] = set()
        if game is not None:
            for proc in self.find_game_processes(game):
                game_pids.add(proc.pid)

        for proc in psutil.process_iter(["pid", "name"]):
            try:
                proc.cpu_percent(interval=None)
            except (psutil.Error, ProcessLookupError, PermissionError):
                continue
        psutil.cpu_percent(interval=0.12)

        rows: list[ThrottleCandidate] = []
        for proc in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                info = proc.info
                name = str(info.get("name") or "unknown")
                pid = int(info["pid"])
                if self._is_protected(name, pid, game_pids):
                    continue
                cpu = float(proc.cpu_percent(interval=None) or 0.0)
                if cpu < 1.2:
                    continue
                mem = info.get("memory_info")
                memory_mb = (mem.rss / (1024 * 1024)) if mem else 0.0
                rows.append(
                    ThrottleCandidate(
                        pid=pid,
                        name=name,
                        cpu_percent=cpu,
                        memory_mb=memory_mb,
                    )
                )
            except (psutil.Error, ProcessLookupError, PermissionError):
                continue

        rows.sort(key=lambda p: (p.cpu_percent, p.memory_mb), reverse=True)
        return rows[:limit]

    def _priority_value(self, profile: BoostProfile):
        if hasattr(psutil, "HIGH_PRIORITY_CLASS"):
            mapping = {
                "high": psutil.HIGH_PRIORITY_CLASS,
                "above_normal": getattr(
                    psutil, "ABOVE_NORMAL_PRIORITY_CLASS", psutil.HIGH_PRIORITY_CLASS
                ),
                "normal": getattr(psutil, "NORMAL_PRIORITY_CLASS", 0x20),
                "below_normal": getattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS", 0x4000),
            }
            return mapping.get(profile.priority, psutil.HIGH_PRIORITY_CLASS)
        mapping = {"high": -7, "above_normal": -5, "normal": 0, "below_normal": 5}
        return mapping.get(profile.priority, -5)

    def _below_normal_value(self):
        if hasattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS"):
            return psutil.BELOW_NORMAL_PRIORITY_CLASS
        return 5

    def _is_protected(self, name: str, pid: int, game_pids: set[int]) -> bool:
        if pid in game_pids or pid == 0 or pid == 4:
            return True
        if pid == psutil.Process().pid:
            return True
        lowered = name.lower()
        if lowered in _PROTECTED_NAMES:
            return True
        if lowered.startswith("pingvault"):
            return True
        return False

    def _proc_meta(self, proc: psutil.Process) -> tuple[str, float]:
        try:
            name = proc.name()
        except (psutil.Error, ProcessLookupError, PermissionError):
            name = f"pid-{proc.pid}"
        try:
            create_time = float(proc.create_time())
        except (psutil.Error, ProcessLookupError, PermissionError):
            create_time = 0.0
        return name, create_time

    def _persist_ledger(self) -> None:
        data = BoostLedger(
            active=self.is_active,
            game_id=self._active_game_id or "",
            game_name=self._active_game.name if self._active_game else "",
            timer_raised=bool(self._tune._timer_active),  # noqa: SLF001
            previous_power_scheme=self._tune.state.previous_power_scheme,
            dns_flushed=self._dns_flushed,
            entries=[],
        )
        for item in self._priority_restores:
            data.entries.append(
                LedgerEntry(
                    kind="priority",
                    pid=item.pid,
                    name=item.name,
                    nice=item.nice,
                    create_time=item.create_time,
                )
            )
        for item in self._throttled_restores:
            data.entries.append(
                LedgerEntry(
                    kind="background",
                    pid=item.pid,
                    name=item.name,
                    nice=item.nice,
                    create_time=item.create_time,
                )
            )
        self._ledger.data = data
        self._ledger.save()

    def _record_change(
        self,
        *,
        kind: str,
        proc: psutil.Process,
        previous_nice: int | float,
    ) -> None:
        name, create_time = self._proc_meta(proc)
        entry = _PriorityRestore(
            pid=proc.pid,
            nice=previous_nice,
            name=name,
            create_time=create_time,
            kind=kind,
        )
        bucket = self._priority_restores if kind == "priority" else self._throttled_restores
        bucket[:] = [item for item in bucket if item.pid != proc.pid]
        bucket.append(entry)
        # Write ledger BEFORE relying on the change surviving a crash.
        self._persist_ledger()

    def _throttle_background(
        self,
        profile: BoostProfile,
        game_pids: set[int],
        exclude_pids: set[int],
    ) -> list[str]:
        if not profile.throttle_background:
            return []

        notes: list[str] = []
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                proc.cpu_percent(interval=None)
            except (psutil.Error, ProcessLookupError, PermissionError):
                continue
        psutil.cpu_percent(interval=0.12)

        candidates: list[tuple[float, psutil.Process, str, int | float]] = []
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                info = proc.info
                name = str(info.get("name") or "unknown")
                pid = int(info["pid"])
                if pid in exclude_pids:
                    continue
                if self._is_protected(name, pid, game_pids):
                    continue
                if any(item.pid == pid for item in self._throttled_restores):
                    continue
                cpu = float(proc.cpu_percent(interval=None) or 0.0)
                if cpu < 1.5:
                    continue
                current_nice = proc.nice()
                candidates.append((cpu, proc, name, current_nice))
            except (psutil.Error, ProcessLookupError, PermissionError):
                continue

        candidates.sort(key=lambda item: item[0], reverse=True)
        below = self._below_normal_value()
        throttled = 0
        for cpu, proc, name, current_nice in candidates[: profile.background_top_n]:
            try:
                # Ledger first, then mutate.
                self._record_change(kind="background", proc=proc, previous_nice=current_nice)
                proc.nice(below)
                throttled += 1
                notes.append(f"背景降速 {name} ({cpu:.0f}% → below_normal)")
            except (psutil.Error, ProcessLookupError, PermissionError):
                # Roll back ledger entry if mutate failed.
                self._throttled_restores = [
                    i for i in self._throttled_restores if i.pid != proc.pid
                ]
                self._persist_ledger()
                continue

        if exclude_pids:
            notes.append(f"已排除 {len(exclude_pids)} 個程序不降速")
        if throttled == 0:
            notes.append("沒有需要降速的高負載背景程序")
        else:
            notes.append(f"已降低 {throttled} 個背景程序優先權")
        return notes

    def boost_game(
        self,
        game: Game,
        exclude_pids: tuple[int, ...] | set[int] | None = None,
    ) -> BoostResult:
        exclude = set(exclude_pids or ())

        # Stop clicked while this boost was still queued / previous session live.
        if self._aborted():
            return self.stop_boost()

        if self.is_active:
            # Internal replace — do not treat as user cancel.
            was_cancel = self._stop_requested
            self._stop_requested = False
            self.stop_boost()
            self._stop_requested = was_cancel
            if self._aborted():
                return self.stop_boost()

        profile = profile_for(game)
        processes = self.find_game_processes(game)
        named: list[str] = []
        for p in processes:
            try:
                named.append(f"{p.name()} ({p.pid})")
            except (psutil.Error, ProcessLookupError, PermissionError):
                named.append(f"PID {p.pid}")
        detected = tuple(named)

        steps: list[str] = [f"方案：{profile.title}"]
        self._dns_flushed = False
        self._power_changed = False
        self._exclude_pids = exclude
        self._bg_watch.clear()
        # Mark session early so ledger writes are active=true.
        self._active_game = game
        self._active_game_id = game.id

        if self._aborted():
            return self.stop_boost()

        if not processes:
            if profile.flush_dns:
                note = self._tune.flush_dns()
                steps.append(note)
                self._dns_flushed = "已刷新" in note
            if self._aborted():
                return self.stop_boost()
            if profile.high_timer_resolution:
                steps.append(self._tune.enable_high_timer_resolution())
            if profile.high_performance_power:
                note = self._tune.enable_high_performance_power()
                steps.append(note)
                self._power_changed = "已切換" in note or "已是高效能" in note
            if self._aborted():
                return self.stop_boost()
            self._active_game = game
            self._active_game_id = game.id
            self._persist_ledger()
            self._last_steps = steps
            return BoostResult(
                status=BoostStatus.WAITING,
                profile=profile,
                applied_steps=tuple(steps),
                detected_processes=(),
                message=(
                    f"「{profile.title}」已待命：尚未偵測到 {game.name}。"
                    f"系統預優化已先套用，開啟遊戲後會自動提高程序優先權。"
                ),
            )

        affected: list[int] = []
        confirmed: list[str] = []
        errors: list[str] = []
        priority = self._priority_value(profile)
        game_pids: set[int] = set()

        for proc in processes:
            if self._aborted():
                return self.stop_boost()
            try:
                previous = proc.nice()
                self._record_change(kind="priority", proc=proc, previous_nice=previous)
                proc.nice(priority)
                current = proc.nice()
                affected.append(proc.pid)
                game_pids.add(proc.pid)
                confirmed.append(f"{proc.name()} → {profile.priority}（確認 {current}）")
            except (psutil.Error, ProcessLookupError, PermissionError) as exc:
                self._priority_restores = [
                    i for i in self._priority_restores if i.pid != proc.pid
                ]
                self._persist_ledger()
                errors.append(f"PID {proc.pid}: {exc}")

        if not affected:
            self._ledger.clear()
            self._reset_session_state()
            return BoostResult(
                status=BoostStatus.DENIED,
                profile=profile,
                applied_steps=tuple(steps),
                detected_processes=detected,
                message=(
                    f"已偵測到 {game.name}，但無法提升優先權"
                    "（請以系統管理員執行 PingVault）。"
                    + ((" " + "；".join(errors)) if errors else "")
                ),
            )

        steps.append(f"偵測到遊戲程序：{', '.join(detected)}")
        steps.extend(confirmed)
        steps.append(f"遊戲優先權 → {profile.priority}（{len(affected)} 程序，已確認）")
        steps.append("已寫入崩潰還原 ledger")
        if self._aborted():
            return self.stop_boost()
        steps.extend(self._throttle_background(profile, game_pids, exclude))
        if self._aborted():
            return self.stop_boost()

        if profile.flush_dns:
            note = self._tune.flush_dns()
            steps.append(note)
            self._dns_flushed = "已刷新" in note
        if profile.high_timer_resolution:
            steps.append(self._tune.enable_high_timer_resolution())
        if profile.high_performance_power:
            note = self._tune.enable_high_performance_power()
            steps.append(note)
            self._power_changed = "已切換" in note or "已是高效能" in note

        if self._aborted():
            return self.stop_boost()

        self._active_game = game
        self._active_game_id = game.id
        self._persist_ledger()
        self._last_steps = steps

        msg = (
            f"「{profile.title}」已套用到 {game.name}。"
            f"已確認 {len(affected)} 個程序優先權，並啟用持續背景平衡。"
        )
        if errors:
            msg += " 部分程序優先權失敗。"
        return BoostResult(
            status=BoostStatus.SUCCESS,
            profile=profile,
            message=msg,
            affected_pids=tuple(affected),
            applied_steps=tuple(steps),
            detected_processes=detected,
        )

    def maintain_boost(self) -> BoostResult | None:
        """Continuous pass while a session is active (call every ~2–3s)."""
        if self._aborted() or not self.is_active or self._active_game is None:
            return None

        game = self._active_game
        profile = profile_for(game)
        notes: list[str] = []
        processes = self.find_game_processes(game)
        game_pids = {p.pid for p in processes}

        if not processes:
            # Stay armed / waiting — arm timer in UI also retries full boost.
            return BoostResult(
                status=BoostStatus.WAITING,
                profile=profile,
                message="維持中：尚未看到遊戲程序",
                applied_steps=tuple(self._last_steps),
                maintain_notes=("等待遊戲程序…",),
            )

        # Keep game priority pinned.
        priority = self._priority_value(profile)
        for proc in processes:
            try:
                current = proc.nice()
                if current != priority:
                    if not any(i.pid == proc.pid for i in self._priority_restores):
                        self._record_change(
                            kind="priority", proc=proc, previous_nice=current
                        )
                    proc.nice(priority)
                    notes.append(f"重新鎖定 {proc.name()} 優先權")
            except (psutil.Error, ProcessLookupError, PermissionError):
                continue

        if not profile.throttle_background:
            self._persist_ledger()
            return BoostResult(
                status=BoostStatus.SUCCESS,
                profile=profile,
                message="維持中",
                applied_steps=tuple(self._last_steps),
                detected_processes=tuple(f"{p.pid}" for p in processes),
                maintain_notes=tuple(notes) or ("遊戲優先權穩定",),
            )

        # Warm CPU samples.
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                proc.cpu_percent(interval=None)
            except (psutil.Error, ProcessLookupError, PermissionError):
                continue
        psutil.cpu_percent(interval=0.08)

        below = self._below_normal_value()
        throttled_pids = {i.pid for i in self._throttled_restores}

        # Demote newly busy background processes (hysteresis).
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                info = proc.info
                name = str(info.get("name") or "unknown")
                pid = int(info["pid"])
                if pid in self._exclude_pids or self._is_protected(name, pid, game_pids):
                    continue
                cpu = float(proc.cpu_percent(interval=None) or 0.0)
                watch = self._bg_watch.setdefault(pid, _BgWatch())
                if pid in throttled_pids:
                    if cpu < 2.0:
                        watch.calm_hits += 1
                        watch.busy_hits = 0
                    else:
                        watch.calm_hits = 0
                    if watch.calm_hits >= 3:
                        # Restore this background process.
                        item = next(
                            (i for i in self._throttled_restores if i.pid == pid), None
                        )
                        if item is not None:
                            try:
                                psutil.Process(pid).nice(item.nice)
                            except (psutil.Error, ProcessLookupError, PermissionError):
                                pass
                            self._throttled_restores = [
                                i for i in self._throttled_restores if i.pid != pid
                            ]
                            notes.append(f"背景恢復 {name}")
                        watch.calm_hits = 0
                    continue

                if cpu >= 8.0:
                    watch.busy_hits += 1
                    watch.calm_hits = 0
                else:
                    watch.busy_hits = 0

                if watch.busy_hits >= 2 and len(self._throttled_restores) < profile.background_top_n:
                    previous = proc.nice()
                    self._record_change(kind="background", proc=proc, previous_nice=previous)
                    proc.nice(below)
                    notes.append(f"持續降載 {name} ({cpu:.0f}%)")
                    watch.busy_hits = 0
            except (psutil.Error, ProcessLookupError, PermissionError):
                continue

        self._persist_ledger()
        return BoostResult(
            status=BoostStatus.SUCCESS,
            profile=profile,
            message="維持中：持續背景平衡",
            applied_steps=tuple(self._last_steps),
            detected_processes=tuple(
                f"{self._proc_meta(p)[0]} ({p.pid})" for p in processes
            ),
            maintain_notes=tuple(notes) if notes else ("背景負載平穩",),
        )

    def _restore_ledger_entries(self, data: BoostLedger) -> list[str]:
        notes: list[str] = []
        for entry in data.entries:
            try:
                proc = psutil.Process(entry.pid)
                if entry.create_time:
                    try:
                        if abs(proc.create_time() - entry.create_time) > 1.0:
                            notes.append(f"略過 PID {entry.pid}（程序已替換）")
                            continue
                    except (psutil.Error, ProcessLookupError, PermissionError):
                        pass
                proc.nice(entry.nice)
                notes.append(f"已還原 {entry.name or entry.pid}（{entry.kind}）")
            except (psutil.Error, ProcessLookupError, PermissionError):
                notes.append(f"無法還原 PID {entry.pid}（可能已結束）")
        return notes

    def stop_boost(self) -> BoostResult:
        self._stop_requested = True
        steps: list[str] = []
        restore_items: list[RestoreItem] = []

        try:
            # Prefer live restore lists; fall back to ledger file.
            ledger = self._ledger.load()
            if (
                not self._priority_restores
                and not self._throttled_restores
                and ledger.entries
            ):
                steps.extend(self._restore_ledger_entries(ledger))

            game_ok = True
            game_count = len(self._priority_restores)
            for item in list(self._priority_restores):
                try:
                    proc = psutil.Process(item.pid)
                    if item.create_time:
                        try:
                            if abs(proc.create_time() - item.create_time) > 1.0:
                                game_ok = False
                                continue
                        except (psutil.Error, ProcessLookupError, PermissionError):
                            pass
                    proc.nice(item.nice)
                except (psutil.Error, ProcessLookupError, PermissionError):
                    game_ok = False
            if game_count:
                steps.append(f"已還原 {game_count} 個遊戲程序優先權")
                restore_items.append(RestoreItem(f"遊戲優先權（{game_count}）", game_ok))
            else:
                restore_items.append(RestoreItem("遊戲優先權", True))

            restored_bg = 0
            bg_total = len(self._throttled_restores)
            for item in list(self._throttled_restores):
                try:
                    psutil.Process(item.pid).nice(item.nice)
                    restored_bg += 1
                except (psutil.Error, ProcessLookupError, PermissionError):
                    continue
            if bg_total:
                steps.append(f"已還原 {restored_bg}/{bg_total} 個背景程序優先權")
                restore_items.append(
                    RestoreItem(
                        f"背景優先權（{restored_bg}/{bg_total}）",
                        restored_bg == bg_total,
                    )
                )
            else:
                restore_items.append(RestoreItem("背景優先權（無變更）", True))

            timer_note = self._tune.disable_high_timer_resolution()
            steps.append(timer_note)
            restore_items.append(RestoreItem("計時器", "失敗" not in timer_note))

            power_note = self._tune.restore_power_scheme()
            steps.append(power_note)
            restore_items.append(RestoreItem("電源方案", "失敗" not in power_note))

            restore_items.append(RestoreItem("DNS（刷新不可還原）", True))
            if self._dns_flushed or ledger.dns_flushed:
                steps.append("DNS 快取曾刷新（無法還原，屬正常）")

            restore_items.append(RestoreItem("崩潰 ledger 已清除", True))
            steps.append("已清除崩潰還原 ledger")
        finally:
            try:
                self._ledger.clear()
            except Exception:
                pass
            self._reset_session_state()
            # Keep _stop_requested True until UI starts a new boost (clear_stop).
            self._stop_requested = True

        self._last_steps = steps
        return BoostResult(
            status=BoostStatus.STOPPED,
            message="加速已停止，請核對下方還原檢查表。",
            applied_steps=tuple(steps),
            restore_items=tuple(restore_items),
        )
