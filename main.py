from __future__ import annotations

import atexit
import signal
import sys

from pingvault.services.admin import ensure_admin
from pingvault.services.session_restore import restore_all


def _install_exit_hooks() -> None:
    """Best-effort restore on abrupt exit (Task Manager may still skip these)."""
    atexit.register(restore_all)

    def _signal_restore(signum, frame) -> None:  # noqa: ANN001
        try:
            restore_all()
        finally:
            raise SystemExit(0)

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _signal_restore)
        except (ValueError, OSError):
            pass


def main() -> int:
    # Ask for elevation before creating the UI (UAC prompt on launch).
    ensure_admin()

    # If last run was force-killed, restore boost / paused apps before UI.
    restore_all()
    _install_exit_hooks()

    from PySide6.QtWidgets import QApplication, QSystemTrayIcon

    from pingvault.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("PingVault")
    app.setOrganizationName("PingVault")
    # Keep process alive when main window is hidden to tray.
    if QSystemTrayIcon.isSystemTrayAvailable():
        app.setQuitOnLastWindowClosed(False)

    window = MainWindow()
    app.aboutToQuit.connect(window.shutdown_restore)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
