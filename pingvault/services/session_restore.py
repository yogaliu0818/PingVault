from __future__ import annotations

"""Disk-backed emergency restore for force-kill / crash / abrupt exit.

Live UI shutdown should prefer the in-process Optimizer/AppPauseManager.
This module only reads ledgers on disk — safe from atexit and startup.
"""


def restore_all() -> list[str]:
    notes: list[str] = []

    try:
        from pingvault.services.optimizer import Optimizer

        opt = Optimizer()
        # Optimizer.__init__ already ran recover_from_ledger once.
        startup = getattr(opt, "startup_recovery_notes", ()) or ()
        notes.extend(str(n) for n in startup)
    except Exception as exc:
        notes.append(f"加速狀態還原失敗：{exc}")

    try:
        from pingvault.services.app_pause import AppPauseManager

        pause = AppPauseManager()
        resume = getattr(pause, "startup_resume", None)
        if resume is not None and resume.resumed:
            notes.append(resume.message)
            notes.extend(f"恢復 {n}" for n in resume.resumed[:8])
        elif resume is not None and resume.message:
            notes.append(resume.message)
    except Exception as exc:
        notes.append(f"暫停程式還原失敗：{exc}")

    return notes
