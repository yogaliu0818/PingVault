from __future__ import annotations

import platform
import re
import subprocess
from dataclasses import dataclass, field


def _run(cmd: list[str], timeout: float = 8.0) -> tuple[bool, str]:
    creation = 0
    if platform.system().lower() == "windows":
        creation = subprocess.CREATE_NO_WINDOW
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=creation,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        return completed.returncode == 0, output.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)


@dataclass
class SystemTuneState:
    timer_raised: bool = False
    previous_power_scheme: str | None = None
    notes: list[str] = field(default_factory=list)


class SystemTune:
    """OS-level tweaks that can be applied for a boost session and later restored."""

    HIGH_PERFORMANCE_GUID = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"

    def __init__(self) -> None:
        self.state = SystemTuneState()
        self._timer_active = False

    def flush_dns(self) -> str:
        if platform.system().lower() != "windows":
            return "DNS 刷新略過（非 Windows）"
        ok, output = _run(["ipconfig", "/flushdns"])
        if ok:
            return "已刷新 DNS 快取"
        return f"DNS 刷新失敗：{output[:120]}"

    def enable_high_timer_resolution(self) -> str:
        if platform.system().lower() != "windows":
            return "計時器優化略過（非 Windows）"
        try:
            import ctypes

            result = ctypes.windll.winmm.timeBeginPeriod(1)
            if result == 0:
                self._timer_active = True
                self.state.timer_raised = True
                return "已啟用 1ms 高解析計時器"
            return f"計時器優化失敗（code={result}）"
        except Exception as exc:  # noqa: BLE001
            return f"計時器優化失敗：{exc}"

    def disable_high_timer_resolution(self) -> str:
        if not self._timer_active:
            return "計時器無需還原"
        try:
            import ctypes

            ctypes.windll.winmm.timeEndPeriod(1)
            self._timer_active = False
            self.state.timer_raised = False
            return "已還原系統計時器"
        except Exception as exc:  # noqa: BLE001
            return f"計時器還原失敗：{exc}"

    def _current_power_scheme(self) -> str | None:
        ok, output = _run(["powercfg", "/getactivescheme"])
        if not ok:
            return None
        match = re.search(
            r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
            output,
        )
        return match.group(1) if match else None

    def enable_high_performance_power(self) -> str:
        if platform.system().lower() != "windows":
            return "電源方案略過（非 Windows）"
        current = self._current_power_scheme()
        if current:
            self.state.previous_power_scheme = current
        if current and current.lower() == self.HIGH_PERFORMANCE_GUID.lower():
            return "已是高效能電源方案"
        ok, output = _run(["powercfg", "/setactive", self.HIGH_PERFORMANCE_GUID])
        if ok:
            return "已切換至高效能電源方案"
        return f"電源方案切換失敗：{output[:120]}（可略過）"

    def restore_power_scheme(self) -> str:
        previous = self.state.previous_power_scheme
        if not previous:
            return "電源方案無需還原"
        if previous.lower() == self.HIGH_PERFORMANCE_GUID.lower():
            self.state.previous_power_scheme = None
            return "電源方案維持高效能"
        ok, output = _run(["powercfg", "/setactive", previous])
        self.state.previous_power_scheme = None
        if ok:
            return "已還原原本電源方案"
        return f"電源方案還原失敗：{output[:120]}"
