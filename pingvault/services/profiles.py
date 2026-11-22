from __future__ import annotations

from dataclasses import dataclass

from .games import Game


@dataclass(frozen=True)
class BoostProfile:
    id: str
    title: str
    summary: str
    # Windows priority: high | above_normal | normal
    priority: str
    ping_count: int
    ping_timeout_ms: int
    watch_interval_ms: int
    focus: tuple[str, ...]
    # Capability flags
    throttle_background: bool = True
    background_top_n: int = 6
    flush_dns: bool = True
    high_timer_resolution: bool = True
    high_performance_power: bool = True


_PROFILES: dict[str, BoostProfile] = {
    "fps": BoostProfile(
        id="fps_competitive",
        title="競技射擊方案",
        summary="最高優先權＋壓低背景負載＋DNS／計時器優化，偏競技低延遲。",
        priority="high",
        ping_count=6,
        ping_timeout_ms=1500,
        watch_interval_ms=2500,
        focus=("低延遲", "高優先權", "背景降速", "DNS刷新"),
        throttle_background=True,
        background_top_n=8,
        flush_dns=True,
        high_timer_resolution=True,
        high_performance_power=True,
    ),
    "battle_royale": BoostProfile(
        id="br_stability",
        title="大逃殺穩定方案",
        summary="高優先權＋背景降速＋高效能電源，兼顧延遲與長局穩定。",
        priority="high",
        ping_count=5,
        ping_timeout_ms=1800,
        watch_interval_ms=2800,
        focus=("連線穩定", "高優先權", "背景降速", "電源優化"),
        throttle_background=True,
        background_top_n=7,
        flush_dns=True,
        high_timer_resolution=True,
        high_performance_power=True,
    ),
    "moba": BoostProfile(
        id="moba_latency",
        title="MOBA 延遲方案",
        summary="提高遊戲優先權、刷新 DNS、壓低佔資源背景，減少操作延遲感。",
        priority="high",
        ping_count=5,
        ping_timeout_ms=1600,
        watch_interval_ms=2600,
        focus=("操作延遲", "高優先權", "背景降速", "DNS刷新"),
        throttle_background=True,
        background_top_n=6,
        flush_dns=True,
        high_timer_resolution=True,
        high_performance_power=True,
    ),
    "mmorpg": BoostProfile(
        id="mmo_session",
        title="MMO 長連線方案",
        summary="溫和提升優先權，輕量背景降速，偏重長時間連線穩定。",
        priority="above_normal",
        ping_count=4,
        ping_timeout_ms=2200,
        watch_interval_ms=3500,
        focus=("長連線", "溫和優先權", "輕量背景降速"),
        throttle_background=True,
        background_top_n=4,
        flush_dns=True,
        high_timer_resolution=False,
        high_performance_power=False,
    ),
    "rpg": BoostProfile(
        id="rpg_balanced",
        title="RPG 平衡方案",
        summary="平衡優先權與背景負載，適合單機／輕連線 RPG。",
        priority="above_normal",
        ping_count=3,
        ping_timeout_ms=2000,
        watch_interval_ms=4000,
        focus=("效能平衡", "背景降速"),
        throttle_background=True,
        background_top_n=5,
        flush_dns=False,
        high_timer_resolution=False,
        high_performance_power=True,
    ),
    "default": BoostProfile(
        id="general",
        title="通用加速方案",
        summary="標準本機優化：優先權、DNS、計時器與背景降速。",
        priority="above_normal",
        ping_count=4,
        ping_timeout_ms=2000,
        watch_interval_ms=3000,
        focus=("通用優化", "背景降速", "延遲監測"),
        throttle_background=True,
        background_top_n=5,
        flush_dns=True,
        high_timer_resolution=True,
        high_performance_power=True,
    ),
}

_GENRE_MAP = {
    "fps": "fps",
    "battle royale": "battle_royale",
    "moba": "moba",
    "mmorpg": "mmorpg",
    "rpg": "rpg",
    "action rpg": "rpg",
    "action": "rpg",
    "survival": "battle_royale",
    "fighting": "fps",
    "strategy": "moba",
    "sandbox": "default",
    "sports": "default",
    "horror": "default",
    "party": "default",
    "rhythm": "default",
    "adventure": "rpg",
    "simulation": "default",
    "racing": "default",
}


def profile_for(game: Game) -> BoostProfile:
    key = _GENRE_MAP.get(game.genre.strip().lower(), "default")
    return _PROFILES[key]
