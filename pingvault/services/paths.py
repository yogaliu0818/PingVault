from __future__ import annotations

import os
import sys
from pathlib import Path


def app_root() -> Path:
    """Directory that contains the `pingvault` package data (dev or frozen)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "pingvault"  # noqa: SLF001
    return Path(__file__).resolve().parent.parent


def package_data_dir() -> Path:
    return app_root() / "data"


def package_assets_dir() -> Path:
    return app_root() / "assets"


def user_data_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    folder = base / "PingVault"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def thumbs_dir() -> Path:
    """Writable thumb cache — never write into Program Files install tree."""
    folder = user_data_dir() / "thumbs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder
