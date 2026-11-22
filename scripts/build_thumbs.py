"""Prebuild small JPEG thumbs so the UI never scales huge covers while scrolling."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QGuiApplication  # noqa: E402

from pingvault.services.games import GameCatalog  # noqa: E402
from pingvault.services.icons import THUMBS_DIR, clear_cover_cache, warm_cover_cache  # noqa: E402


def main() -> None:
    app = QGuiApplication([])
    del app

    if THUMBS_DIR.exists():
        for path in THUMBS_DIR.glob("*.jpg"):
            path.unlink()

    clear_cover_cache()
    ids = [game.id for game in GameCatalog().all()]
    warm_cover_cache(ids)
    print(f"built {len(list(THUMBS_DIR.glob('*.jpg')))} thumbs in {THUMBS_DIR}")


if __name__ == "__main__":
    main()
