from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


def prefs_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    folder = base / "PingVault"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "user_prefs.json"


@dataclass
class GamePrefs:
    exclude_names: list[str] = field(default_factory=list)
    pause_apps: bool | None = None


@dataclass
class UserPrefs:
    pause_apps_default: bool = True
    games: dict[str, GamePrefs] = field(default_factory=dict)

    def game(self, game_id: str) -> GamePrefs:
        if game_id not in self.games:
            self.games[game_id] = GamePrefs()
        return self.games[game_id]

    def to_dict(self) -> dict:
        return {
            "pause_apps_default": self.pause_apps_default,
            "games": {
                gid: {
                    "exclude_names": list(prefs.exclude_names),
                    "pause_apps": prefs.pause_apps,
                }
                for gid, prefs in self.games.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> UserPrefs:
        games: dict[str, GamePrefs] = {}
        raw_games = data.get("games", {})
        if isinstance(raw_games, dict):
            for gid, item in raw_games.items():
                if not isinstance(item, dict):
                    continue
                names = item.get("exclude_names", [])
                games[str(gid)] = GamePrefs(
                    exclude_names=[str(n).lower() for n in names if n],
                    pause_apps=item.get("pause_apps", None),
                )
        return cls(
            pause_apps_default=bool(data.get("pause_apps_default", True)),
            games=games,
        )


class PrefsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or prefs_path()
        self.data = UserPrefs()
        self.load()

    def load(self) -> UserPrefs:
        if not self.path.exists():
            self.data = UserPrefs()
            return self.data
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.data = UserPrefs.from_dict(raw if isinstance(raw, dict) else {})
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            self.data = UserPrefs()
        return self.data

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def exclude_names_for(self, game_id: str) -> set[str]:
        return {n.lower() for n in self.data.game(game_id).exclude_names}

    def set_exclude_names(self, game_id: str, names: set[str] | list[str]) -> None:
        prefs = self.data.game(game_id)
        prefs.exclude_names = sorted({str(n).lower() for n in names if n})
        self.save()

    def pause_apps_for(self, game_id: str | None = None) -> bool:
        if game_id:
            value = self.data.game(game_id).pause_apps
            if value is not None:
                return bool(value)
        return bool(self.data.pause_apps_default)

    def set_pause_apps(self, enabled: bool, game_id: str | None = None) -> None:
        self.data.pause_apps_default = bool(enabled)
        if game_id:
            self.data.game(game_id).pause_apps = bool(enabled)
        self.save()
