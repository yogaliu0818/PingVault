from __future__ import annotations

import os
from dataclasses import dataclass

import psutil


@dataclass(frozen=True)
class SystemStats:
    cpu_percent: float
    memory_percent: float
    memory_used_gb: float
    memory_total_gb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float


class PerformanceMonitor:
    """Samples CPU, memory, and root-disk usage."""

    def __init__(self) -> None:
        # Prime CPU counter so the first real sample is meaningful.
        psutil.cpu_percent(interval=None)
        self._disk_path = "C:\\" if os.name == "nt" else "/"

    def sample(self) -> SystemStats:
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(self._disk_path)

        return SystemStats(
            cpu_percent=float(cpu),
            memory_percent=float(mem.percent),
            memory_used_gb=mem.used / (1024**3),
            memory_total_gb=mem.total / (1024**3),
            disk_percent=float(disk.percent),
            disk_used_gb=disk.used / (1024**3),
            disk_total_gb=disk.total / (1024**3),
        )
