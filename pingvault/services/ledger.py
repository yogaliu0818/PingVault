from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path


def default_ledger_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    folder = base / "PingVault"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "boost_ledger.json"


@dataclass
class LedgerEntry:
    kind: str  # priority | background
    pid: int
    name: str
    nice: int | float
    create_time: float = 0.0


@dataclass
class BoostLedger:
    version: int = 1
    active: bool = False
    game_id: str = ""
    game_name: str = ""
    timer_raised: bool = False
    previous_power_scheme: str | None = None
    dns_flushed: bool = False
    entries: list[LedgerEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "active": self.active,
            "game_id": self.game_id,
            "game_name": self.game_name,
            "timer_raised": self.timer_raised,
            "previous_power_scheme": self.previous_power_scheme,
            "dns_flushed": self.dns_flushed,
            "entries": [asdict(e) for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict) -> BoostLedger:
        entries = [
            LedgerEntry(
                kind=str(item.get("kind", "priority")),
                pid=int(item.get("pid", 0)),
                name=str(item.get("name", "")),
                nice=item.get("nice", 0),
                create_time=float(item.get("create_time", 0.0) or 0.0),
            )
            for item in data.get("entries", [])
            if isinstance(item, dict)
        ]
        return cls(
            version=int(data.get("version", 1)),
            active=bool(data.get("active", False)),
            game_id=str(data.get("game_id", "")),
            game_name=str(data.get("game_name", "")),
            timer_raised=bool(data.get("timer_raised", False)),
            previous_power_scheme=data.get("previous_power_scheme"),
            dns_flushed=bool(data.get("dns_flushed", False)),
            entries=entries,
        )


class LedgerStore:
    """Crash-safe on-disk record of priority changes (write-before-mutate)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_ledger_path()
        self.data = BoostLedger()

    def load(self) -> BoostLedger:
        if not self.path.exists():
            self.data = BoostLedger()
            return self.data
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.data = BoostLedger.from_dict(raw if isinstance(raw, dict) else {})
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            self.data = BoostLedger()
        return self.data

    def save(self) -> None:
        payload = json.dumps(self.data.to_dict(), ensure_ascii=False, indent=2)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix="pingvault_ledger_",
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

    def clear(self) -> None:
        self.data = BoostLedger()
        try:
            if self.path.exists():
                self.path.unlink()
        except OSError:
            self.save()

    def upsert_entry(self, entry: LedgerEntry) -> None:
        for i, existing in enumerate(self.data.entries):
            if existing.pid == entry.pid and existing.kind == entry.kind:
                self.data.entries[i] = entry
                return
        self.data.entries.append(entry)

    def remove_pid(self, pid: int, kind: str | None = None) -> None:
        self.data.entries = [
            e
            for e in self.data.entries
            if not (e.pid == pid and (kind is None or e.kind == kind))
        ]
