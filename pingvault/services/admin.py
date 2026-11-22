from __future__ import annotations

import ctypes
import os
import subprocess
import sys


def is_admin() -> bool:
    if sys.platform != "win32":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _message_box(text: str, title: str = "PingVault") -> None:
    try:
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)  # MB_ICONERROR
    except Exception:
        print(text, file=sys.stderr)


def _skip_elevation() -> bool:
    if "--no-admin" in sys.argv:
        return True
    flag = os.environ.get("PINGVAULT_NO_ADMIN", "").strip().lower()
    return flag in {"1", "true", "yes"}


def ensure_admin() -> None:
    """
    On Windows, relaunch via UAC if this process is not elevated.
    Exits the current process after starting the elevated child (or on cancel).
    """
    if sys.platform != "win32":
        return
    if is_admin() or _skip_elevation():
        return

    if getattr(sys, "frozen", False):
        # Packaged PingVault.exe
        executable = sys.executable
        params = subprocess.list2cmdline(sys.argv[1:])
        cwd = os.path.dirname(executable) or None
    else:
        # python main.py …
        executable = sys.executable
        script = os.path.abspath(sys.argv[0])
        params = subprocess.list2cmdline([script, *sys.argv[1:]])
        cwd = os.getcwd()

    # ShellExecuteW returns value > 32 on success.
    result = int(
        ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            executable,
            params,
            cwd,
            1,  # SW_SHOWNORMAL
        )
    )
    if result <= 32:
        _message_box(
            "PingVault 需要系統管理員權限才能提升遊戲優先權與刷新 DNS。\n\n"
            "請重新開啟，並在 UAC 視窗按「是」。"
        )
        raise SystemExit(1)
    # Elevated instance is starting; exit this non-elevated process.
    raise SystemExit(0)


ADMIN_HELP = (
    "提升遊戲優先權需要系統管理員權限。\n\n"
    "請關閉 PingVault 後重新開啟，並在 UAC 提示時按「是」。\n"
    "若捷徑未觸發提權，請對 PingVault.exe 右鍵 →「以系統管理員身分執行」。\n\n"
    "沒有管理員時，DNS 刷新與部分優先權變更可能會失敗。"
)
