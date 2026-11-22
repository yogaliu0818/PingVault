from __future__ import annotations

import platform
import re
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class ThermalStats:
    cpu_c: float | None
    gpu_c: float | None
    gpu_name: str | None = None
    source_cpu: str = ""
    source_gpu: str = ""


class ThermalMonitor:
    """Best-effort CPU/GPU temperature reader for Windows."""

    def __init__(self) -> None:
        self._nvml_ok: bool | None = None
        self._gpu_name: str | None = None

    def sample(self) -> ThermalStats:
        cpu_c, cpu_src = self._read_cpu_temp()
        gpu_c, gpu_src, gpu_name = self._read_gpu_temp()
        return ThermalStats(
            cpu_c=cpu_c,
            gpu_c=gpu_c,
            gpu_name=gpu_name,
            source_cpu=cpu_src,
            source_gpu=gpu_src,
        )

    def _read_cpu_temp(self) -> tuple[float | None, str]:
        if platform.system().lower() != "windows":
            return None, "unsupported"
        # ACPI thermal zones (tenths of Kelvin). Often board/zone sensors, not
        # package exact, but usable without extra drivers.
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature "
            "-ErrorAction SilentlyContinue | Select-Object -ExpandProperty CurrentTemperature",
        ]
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            values: list[float] = []
            for token in re.findall(r"\d+", completed.stdout or ""):
                kelvin_tenths = float(token)
                celsius = kelvin_tenths / 10.0 - 273.15
                if 20.0 <= celsius <= 110.0:
                    values.append(celsius)
            if values:
                return max(values), "acpi"
        except (OSError, subprocess.TimeoutExpired, ValueError):
            pass
        return None, "unavailable"

    def _read_gpu_temp(self) -> tuple[float | None, str, str | None]:
        # NVIDIA via NVML if installed.
        try:
            import pynvml  # type: ignore

            if self._nvml_ok is not True:
                pynvml.nvmlInit()
                self._nvml_ok = True
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            if self._gpu_name is None:
                raw = pynvml.nvmlDeviceGetName(handle)
                self._gpu_name = raw.decode() if isinstance(raw, bytes) else str(raw)
            temp = float(
                pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            )
            return temp, "nvml", self._gpu_name
        except Exception:
            self._nvml_ok = False

        # Fallback: nvidia-smi
        try:
            completed = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=temperature.gpu,name",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW
                if platform.system().lower() == "windows"
                else 0,
            )
            line = (completed.stdout or "").strip().splitlines()[0]
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 1:
                temp = float(parts[0])
                name = parts[1] if len(parts) > 1 else "NVIDIA GPU"
                return temp, "nvidia-smi", name
        except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
            pass

        return None, "unavailable", None
