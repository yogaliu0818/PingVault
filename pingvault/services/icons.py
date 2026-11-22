from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

from pingvault.services.paths import package_assets_dir, thumbs_dir


def _icons_dir() -> Path:
    return package_assets_dir() / "icons"


def icon_path_for(game_id: str) -> Path | None:
    icons = _icons_dir()
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        path = icons / f"{game_id}{ext}"
        if path.exists():
            return path
    return None


def _thumb_path(game_id: str, width: int, height: int) -> Path:
    return thumbs_dir() / f"{game_id}_{width}x{height}.jpg"


def _center_crop_scale(image: QImage, width: int, height: int) -> QImage:
    if image.isNull():
        return image

    src_w, src_h = image.width(), image.height()
    target_ratio = width / height
    src_ratio = src_w / src_h if src_h else target_ratio

    if src_ratio > target_ratio:
        new_w = max(1, int(src_h * target_ratio))
        x = max(0, (src_w - new_w) // 2)
        cropped = image.copy(x, 0, new_w, src_h)
    else:
        new_h = max(1, int(src_w / target_ratio))
        y = max(0, (src_h - new_h) // 2)
        cropped = image.copy(0, y, src_w, new_h)

    return cropped.scaled(
        width,
        height,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def ensure_thumb(game_id: str, width: int, height: int) -> Path | None:
    """Create a small JPEG thumb once; reuse forever for smooth scrolling."""
    thumb = _thumb_path(game_id, width, height)
    if thumb.exists() and thumb.stat().st_size > 500:
        return thumb

    source_path = icon_path_for(game_id)
    if source_path is None:
        return None

    image = QImage(str(source_path))
    if image.isNull():
        return None

    scaled = _center_crop_scale(image, width, height)
    if scaled.isNull():
        return None

    # Opaque RGB JPEG — much cheaper to paint while scrolling than huge PNGs.
    try:
        scaled.convertToFormat(QImage.Format.Format_RGB888).save(str(thumb), "JPG", 82)
    except Exception:
        return None
    return thumb if thumb.exists() else None


@lru_cache(maxsize=128)
def load_cover(game_id: str, width: int, height: int) -> QPixmap | None:
    thumb = ensure_thumb(game_id, width, height)
    if thumb is None:
        return None
    pixmap = QPixmap(str(thumb))
    return None if pixmap.isNull() else pixmap


def warm_cover_cache(game_ids: list[str], sizes: tuple[tuple[int, int], ...] = ((152, 190), (96, 120))) -> None:
    for game_id in game_ids:
        for width, height in sizes:
            ensure_thumb(game_id, width, height)
            load_cover(game_id, width, height)


def clear_cover_cache() -> None:
    load_cover.cache_clear()
