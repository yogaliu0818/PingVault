from __future__ import annotations

import json
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path

import psutil

# Common background hogs safe to suspend during a boost session.
DEFAULT_PAUSE_NAMES = {
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "brave.exe",
    "opera.exe",
    "onedrive.exe",
    "dropbox.exe",
    "googledrivefs.exe",
    "googlecrashhandler.exe",
    "googlecrashhandler64.exe",
    "microsoftedgeupdate.exe",
    "googleupdate.exe",
    "teams.exe",
    "ms-teams.exe",
    "slack.exe",
    "spotify.exe",
    "adobeupdater.exe",
    "ccxprocess.exe",
    "creative cloud.exe",
    "itunes.exe",
    "applemobiledeviceservice.exe",
}

# Never suspend these even if names collide.
_NEVER_PAUSE = {
    "csrss.exe",
    "winlogon.exe",
    "services.exe",
    "lsass.exe",
    "svchost.exe",
    "dwm.exe",
    "explorer.exe",
    "python.exe",
    "pythonw.exe",
    "discord.exe",
    "obs64.exe",
    "obs32.exe",
    "steam.exe",
    "rtss.exe",
}


def _pause_ledger_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    folder = base / "PingVault"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "pause_ledger.json"


@dataclass
class PausedProc:
    pid: int
    name: str
    create_time: float = 0.0


@dataclass
class PauseLedger:
    active: bool = False
    entries: list[PausedProc] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "active": self.active,
            "entries": [asdict(e) for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict) -> PauseLedger:
        entries = [
            PausedProc(
                pid=int(item.get("pid", 0)),
                name=str(item.get("name", "")),
                create_time=float(item.get("create_time", 0.0) or 0.0),
            )
            for item in data.get("entries", [])
            if isinstance(item, dict)
        ]
        return cls(active=bool(data.get("active", False)), entries=entries)


@dataclass(frozen=True)
class PauseResult:
    paused: tuple[str, ...]
    skipped: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class ResumeResult:
    resumed: tuple[str, ...]
    missing: tuple[str, ...]
    message: str


def _identity_ok(proc: psutil.Process, create_time: float) -> bool:
    if not create_time:
        return True
    try:
        return abs(proc.create_time() - create_time) <= 1.0
    except (psutil.Error, ProcessLookupError, PermissionError):
        return True


def _is_suspended(proc: psutil.Process) -> bool:
    try:
        # Windows NtSuspendProcess → psutil reports STATUS_STOPPED.
        return proc.status() == psutil.STATUS_STOPPED
    except (psutil.Error, ProcessLookupError, PermissionError):
        return False


def _wake_process(proc: psutil.Process) -> None:
    """Unwind suspend count and nudge the process so it can page memory back in."""
    # Suspend is reference-counted; resume until no longer stopped (cap attempts).
    for _ in range(16):
        try:
            proc.resume()
        except (psutil.Error, ProcessLookupError, PermissionError):
            return
        if not _is_suspended(proc):
            break

    # Give the process a brief scheduling bump so UI threads run before
    # Windows has fully faulted its working set back from the page file.
    try:
        previous = proc.nice()
        if hasattr(psutil, "ABOVE_NORMAL_PRIORITY_CLASS"):
            proc.nice(psutil.ABOVE_NORMAL_PRIORITY_CLASS)
            proc.nice(previous)
        elif hasattr(psutil, "NORMAL_PRIORITY_CLASS"):
            # At least ensure we are not leaving an odd class behind.
            proc.nice(psutil.NORMAL_PRIORITY_CLASS)
    except (psutil.Error, ProcessLookupError, PermissionError, ValueError):
        pass

    # Touch query APIs — cheap, helps the kernel notice the process is live.
    try:
        with proc.oneshot():
            _ = proc.memory_info()
            _ = proc.num_threads()
    except (psutil.Error, ProcessLookupError, PermissionError):
        pass


class AppPauseManager:
    """Suspend/resume heavy user apps for a boost session (crash-safe ledger)."""

    def __init__(self, names: set[str] | None = None) -> None:
        self.names = {n.lower() for n in (names or DEFAULT_PAUSE_NAMES)}
        self.path = _pause_ledger_path()
        self._paused: list[PausedProc] = []
        self.startup_resume: ResumeResult | None = self.recover()

    @property
    def is_active(self) -> bool:
        return bool(self._paused)

    def list_running_targets(self) -> list[PausedProc]:
        found: list[PausedProc] = []
        for proc in psutil.process_iter(["pid", "name", "create_time"]):
            try:
                info = proc.info
                name = str(info.get("name") or "").lower()
                if name not in self.names or name in _NEVER_PAUSE:
                    continue
                found.append(
                    PausedProc(
                        pid=int(info["pid"]),
                        name=str(info.get("name") or name),
                        create_time=float(info.get("create_time") or 0.0),
                    )
                )
            except (psutil.Error, ProcessLookupError, PermissionError):
                continue
        return found

    def _save(self) -> None:
        ledger = PauseLedger(active=bool(self._paused), entries=list(self._paused))
        payload = json.dumps(ledger.to_dict(), ensure_ascii=False, indent=2)
        fd, tmp_name = tempfile.mkstemp(
            prefix="pingvault_pause_",
            suffix=".json",
            dir=str(self.path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def _clear_file(self) -> None:
        self._paused.clear()
        try:
            if self.path.exists():
                self.path.unlink()
        except OSError:
            self._save()

    def recover(self) -> ResumeResult | None:
        if not self.path.exists():
            return None
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            ledger = PauseLedger.from_dict(raw if isinstance(raw, dict) else {})
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            self._clear_file()
            return None
        if not ledger.active and not ledger.entries:
            return None
        self._paused = list(ledger.entries)
        return self.resume_all()

    def pause_running(self) -> PauseResult:
        # Resume any previous session first.
        if self._paused:
            self.resume_all()

        paused: list[str] = []
        skipped: list[str] = []
        records: list[PausedProc] = []

        targets = self.list_running_targets()
        # Intent ledger once before suspending (faster than save-per-process).
        self._paused = list(targets)
        if targets:
            self._save()
        else:
            self._clear_file()

        for target in targets:
            try:
                proc = psutil.Process(target.pid)
                if not _identity_ok(proc, target.create_time):
                    skipped.append(f"{target.name}#{target.pid}")
                    continue
                proc.suspend()
                records.append(target)
                paused.append(f"{target.name} ({target.pid})")
            except (psutil.Error, ProcessLookupError, PermissionError):
                skipped.append(f"{target.name}#{target.pid}")

        self._paused = list(records)
        if self._paused:
            self._save()
        else:
            self._clear_file()

        if paused:
            msg = f"已暫停 {len(paused)} 個背景程式"
        else:
            msg = "沒有可暫停的瀏覽器／雲端同步程式"
        return PauseResult(tuple(paused), tuple(skipped), msg)

    def _resume_one(self, item: PausedProc) -> tuple[str, bool]:
        """Returns (label, ok). ok False → missing/replaced."""
        label = f"{item.name} ({item.pid})"
        try:
            proc = psutil.Process(item.pid)
            if not _identity_ok(proc, item.create_time):
                return (f"{item.name}#{item.pid}", False)
            _wake_process(proc)
            return (label, True)
        except (psutil.Error, ProcessLookupError, PermissionError):
            return (f"{item.name}#{item.pid}", False)

    def resume_all(self) -> ResumeResult:
        items = list(self._paused)
        if not items:
            # Still try clearing a stale ledger file.
            self._clear_file()
            return ResumeResult((), (), "沒有需要恢復的暫停程式")

        resumed: list[str] = []
        missing: list[str] = []

        # Parallel wake — Chrome/Edge often have many helper processes.
        # During interpreter shutdown (atexit / force-close), stay sequential.
        use_pool = len(items) > 1 and not getattr(sys, "is_finalizing", lambda: False)()
        if use_pool:
            workers = min(16, max(4, len(items)))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(self._resume_one, item) for item in items]
                for fut in as_completed(futures):
                    try:
                        label, ok = fut.result()
                    except Exception:
                        missing.append("unknown")
                        continue
                    if ok:
                        resumed.append(label)
                    else:
                        missing.append(label)
        else:
            for item in items:
                label, ok = self._resume_one(item)
                if ok:
                    resumed.append(label)
                else:
                    missing.append(label)

        self._clear_file()
        msg = f"已快速恢復 {len(resumed)} 個暫停程式"
        if missing:
            msg += f"；{len(missing)} 個已結束"
        return ResumeResult(tuple(resumed), tuple(missing), msg)
