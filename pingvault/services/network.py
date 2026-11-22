from __future__ import annotations

import platform
import re
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class PingResult:
    host: str
    avg_ms: float | None
    min_ms: float | None
    max_ms: float | None
    packet_loss_percent: float
    samples: int
    ok: bool
    message: str = ""


class NetworkMonitor:
    """Runs ICMP ping and parses latency / packet loss."""

    def ping(self, host: str, count: int = 4, timeout_ms: int = 2000) -> PingResult:
        system = platform.system().lower()
        if system == "windows":
            cmd = ["ping", "-n", str(count), "-w", str(timeout_ms), host]
        else:
            timeout_s = max(1, timeout_ms // 1000)
            cmd = ["ping", "-c", str(count), "-W", str(timeout_s), host]

        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_ms / 1000 * count + 5,
                creationflags=subprocess.CREATE_NO_WINDOW if system == "windows" else 0,
            )
            output = (completed.stdout or "") + (completed.stderr or "")
        except (subprocess.TimeoutExpired, OSError) as exc:
            return PingResult(
                host=host,
                avg_ms=None,
                min_ms=None,
                max_ms=None,
                packet_loss_percent=100.0,
                samples=count,
                ok=False,
                message=str(exc),
            )

        return self._parse(host, output, count)

    def _parse(self, host: str, output: str, count: int) -> PingResult:
        loss = self._parse_loss(output)
        times = self._parse_times(output)
        stats = self._parse_rtt_stats(output)

        if stats:
            min_ms, max_ms, avg_ms = stats
        elif times:
            min_ms = min(times)
            max_ms = max(times)
            avg_ms = sum(times) / len(times)
        else:
            min_ms = max_ms = avg_ms = None

        ok = avg_ms is not None and loss < 100
        return PingResult(
            host=host,
            avg_ms=avg_ms,
            min_ms=min_ms,
            max_ms=max_ms,
            packet_loss_percent=loss,
            samples=count,
            ok=ok,
            message="" if ok else "無法取得穩定回應",
        )

    @staticmethod
    def _parse_loss(output: str) -> float:
        # Windows: (25% loss) / (25% 遺失)
        patterns = [
            r"\((\d+(?:\.\d+)?)%\s*(?:loss|遺失|丢失)\)",
            r"(\d+(?:\.\d+)?)%\s*packet\s*loss",
            r"已遺失\s*=\s*\d+\s*\((\d+(?:\.\d+)?)%",
        ]
        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                return float(match.group(1))
        if "100%" in output and ("loss" in output.lower() or "遺失" in output or "丢失" in output):
            return 100.0
        return 0.0 if re.search(r"time[=<]\d+", output, re.IGNORECASE) else 100.0

    @staticmethod
    def _parse_times(output: str) -> list[float]:
        # time=23ms / time<1ms / 時間=23ms
        matches = re.findall(
            r"(?:time|時間|Time)\s*[=<]\s*(\d+(?:\.\d+)?)\s*ms",
            output,
            re.IGNORECASE,
        )
        return [float(m) for m in matches]

    @staticmethod
    def _parse_rtt_stats(output: str) -> tuple[float, float, float] | None:
        # Windows EN: Minimum = 12ms, Maximum = 40ms, Average = 20ms
        # Windows ZH: 最小 = 12ms，最大 = 40ms，平均 = 20ms
        patterns = [
            r"Minimum\s*=\s*(\d+)ms.*?Maximum\s*=\s*(\d+)ms.*?Average\s*=\s*(\d+)ms",
            r"最小\s*=\s*(\d+)ms.*?最大\s*=\s*(\d+)ms.*?平均\s*=\s*(\d+)ms",
            r"rtt min/avg/max/(?:mdev|stddev)\s*=\s*"
            r"(\d+(?:\.\d+))/(\d+(?:\.\d+))/(\d+(?:\.\d+))",
        ]
        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE | re.DOTALL)
            if match:
                groups = match.groups()
                if len(groups) >= 3:
                    # Windows patterns: min, max, avg
                    if "Minimum" in pattern or "最小" in pattern:
                        return float(groups[0]), float(groups[1]), float(groups[2])
                    # Linux pattern: min, avg, max
                    return float(groups[0]), float(groups[2]), float(groups[1])
        return None
