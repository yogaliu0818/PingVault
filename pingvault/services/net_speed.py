from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

import psutil

# Virtual / tunnel adapters inflate totals (often double-count real traffic).
_SKIP_KEYWORDS = (
    "loopback",
    "vethernet",
    "hyper-v",
    "wsl",
    "vmware",
    "virtualbox",
    "vbox",
    "tailscale",
    "nordlynx",
    "wireguard",
    "tap-",
    "tun-",
    "vpn",
    "bluetooth",
    "藍牙",
    "區域連線*",
    "local area connection*",
)


@dataclass(frozen=True)
class NetSpeedStats:
    down_bps: float  # bytes per second (smoothed)
    up_bps: float
    down_text: str
    up_text: str
    iface: str = ""


def format_rate(bps: float) -> str:
    """Stable, human-readable throughput (Task Manager–like Mbps when busy)."""
    if bps < 0:
        bps = 0.0

    kib = bps / 1024.0
    # Idle chatter (Windows background) naturally jitters a few KB/s —
    # quantize so the gauge doesn't flicker 3.2 ↔ 5.7.
    if kib < 12:
        q = int(round(kib))
        if q <= 2:
            return "閒置"
        return f"{q} KB/s"

    mbps = (bps * 8.0) / 1_000_000.0
    if mbps < 1:
        # 12–125 KB/s band: show whole KB/s
        return f"{int(round(kib))} KB/s"
    if mbps < 10:
        return f"{mbps:.1f} Mbps"
    if mbps < 100:
        return f"{mbps:.1f} Mbps"
    return f"{mbps:.0f} Mbps"


def _is_physical(name: str) -> bool:
    lower = name.lower()
    return not any(key in lower for key in _SKIP_KEYWORDS)


def _active_physical_counters() -> dict[str, object]:
    stats = psutil.net_if_stats()
    counters = psutil.net_io_counters(pernic=True)
    out: dict[str, object] = {}
    for name, io in counters.items():
        if not _is_physical(name):
            continue
        st = stats.get(name)
        if st is not None and not st.isup:
            continue
        out[name] = io
    return out


def _primary_io(counters: dict[str, object]) -> tuple[int, int, str]:
    """Use the single busiest physical NIC (not a sum of all)."""
    best_name = ""
    best_recv = 0
    best_sent = 0
    best_total = -1
    for name, io in counters.items():
        r = int(getattr(io, "bytes_recv", 0))
        s = int(getattr(io, "bytes_sent", 0))
        total = r + s
        if total > best_total:
            best_total = total
            best_name = name
            best_recv = r
            best_sent = s
    return best_recv, best_sent, best_name


class NetSpeedMonitor:
    """Realtime NIC throughput: fixed window + rolling median + light EMA."""

    def __init__(self, window: int = 5) -> None:
        self._prev_recv = 0
        self._prev_sent = 0
        self._prev_ts = 0.0
        self._down_hist: deque[float] = deque(maxlen=max(3, window))
        self._up_hist: deque[float] = deque(maxlen=max(3, window))
        self._ema_down = 0.0
        self._ema_up = 0.0
        self._display_down = 0.0
        self._display_up = 0.0
        self._iface = ""
        self._primed = False
        self._prime()

    def _prime(self) -> None:
        recv, sent, iface = _primary_io(_active_physical_counters())
        self._prev_recv = recv
        self._prev_sent = sent
        self._prev_ts = time.perf_counter()
        self._iface = iface
        self._primed = True

    @staticmethod
    def _median(values: deque[float]) -> float:
        data = sorted(values)
        n = len(data)
        if n == 0:
            return 0.0
        mid = n // 2
        if n % 2:
            return data[mid]
        return 0.5 * (data[mid - 1] + data[mid])

    def _stable_display(self, current: float, previous: float) -> float:
        """Hysteresis: ignore tiny swings so UI text stays put."""
        # Below ~12 KB/s, only move if delta ≥ 1.5 KB/s
        if max(current, previous) < 12 * 1024:
            if abs(current - previous) < 1.5 * 1024:
                return previous
            return current
        # Otherwise require ≥12% change (and at least 8 KB/s)
        floor = max(8 * 1024, previous * 0.12)
        if abs(current - previous) < floor:
            return previous
        return current

    def sample(self) -> NetSpeedStats:
        if not self._primed:
            self._prime()

        now = time.perf_counter()
        recv, sent, iface = _primary_io(_active_physical_counters())
        dt = now - self._prev_ts

        # Keep a steady ~1s window; ignore bursty queued callbacks.
        if dt < 0.85:
            return NetSpeedStats(
                down_bps=self._display_down,
                up_bps=self._display_up,
                down_text=format_rate(self._display_down),
                up_text=format_rate(self._display_up),
                iface=self._iface or iface,
            )

        # After a long stall (boost/ping blocked the process), re-baseline.
        if dt > 2.8 or recv < self._prev_recv or sent < self._prev_sent:
            self._prev_recv = recv
            self._prev_sent = sent
            self._prev_ts = now
            self._iface = iface or self._iface
            return NetSpeedStats(
                down_bps=self._display_down,
                up_bps=self._display_up,
                down_text=format_rate(self._display_down),
                up_text=format_rate(self._display_up),
                iface=self._iface,
            )

        raw_down = max(0.0, (recv - self._prev_recv) / dt)
        raw_up = max(0.0, (sent - self._prev_sent) / dt)
        self._prev_recv = recv
        self._prev_sent = sent
        self._prev_ts = now
        self._iface = iface or self._iface

        self._down_hist.append(raw_down)
        self._up_hist.append(raw_up)
        med_down = self._median(self._down_hist)
        med_up = self._median(self._up_hist)

        # Soft EMA on top of median (alpha low = calm).
        a = 0.22
        self._ema_down = med_down if self._ema_down <= 0 else a * med_down + (1 - a) * self._ema_down
        self._ema_up = med_up if self._ema_up <= 0 else a * med_up + (1 - a) * self._ema_up

        self._display_down = self._stable_display(self._ema_down, self._display_down)
        self._display_up = self._stable_display(self._ema_up, self._display_up)

        return NetSpeedStats(
            down_bps=self._display_down,
            up_bps=self._display_up,
            down_text=format_rate(self._display_down),
            up_text=format_rate(self._display_up),
            iface=self._iface,
        )
