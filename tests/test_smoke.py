"""Basic smoke tests for prefs, admin, FPS, and imports."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


class PrefsStoreTests(unittest.TestCase):
    def test_exclude_names_roundtrip(self) -> None:
        from pingvault.services.user_prefs import PrefsStore

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prefs.json"
            store = PrefsStore(path)
            store.set_exclude_names("valorant", {"Chrome.exe", "Discord.exe"})
            again = PrefsStore(path)
            names = again.exclude_names_for("valorant")
            self.assertEqual(names, {"chrome.exe", "discord.exe"})
            self.assertEqual(again.exclude_names_for("other"), set())

    def test_pause_apps_default_and_per_game(self) -> None:
        from pingvault.services.user_prefs import PrefsStore

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prefs.json"
            store = PrefsStore(path)
            self.assertTrue(store.pause_apps_for())
            store.set_pause_apps(False)
            self.assertFalse(store.pause_apps_for())
            store.set_pause_apps(True, game_id="cs2")
            self.assertTrue(store.pause_apps_for("cs2"))
            self.assertTrue(store.pause_apps_for())
            store.set_pause_apps(False, game_id="cs2")
            again = PrefsStore(path)
            self.assertFalse(again.pause_apps_for("cs2"))
            self.assertFalse(again.pause_apps_for())


class AdminTests(unittest.TestCase):
    def test_admin_helpers(self) -> None:
        from pingvault.services.admin import ADMIN_HELP, ensure_admin, is_admin

        self.assertIsInstance(is_admin(), bool)
        self.assertTrue(callable(ensure_admin))
        self.assertIn("系統管理員", ADMIN_HELP)
        self.assertIn("UAC", ADMIN_HELP)

    def test_ensure_admin_respects_skip_env(self) -> None:
        import os

        from pingvault.services.admin import ensure_admin

        prev = os.environ.get("PINGVAULT_NO_ADMIN")
        os.environ["PINGVAULT_NO_ADMIN"] = "1"
        try:
            ensure_admin()  # must not raise / relaunch
        finally:
            if prev is None:
                os.environ.pop("PINGVAULT_NO_ADMIN", None)
            else:
                os.environ["PINGVAULT_NO_ADMIN"] = prev


class FpsTests(unittest.TestCase):
    def test_fps_sample_shape(self) -> None:
        from pingvault.services.fps import FpsMonitor, FpsSample

        sample = FpsMonitor().sample()
        self.assertIsInstance(sample, FpsSample)
        self.assertIn(sample.source, {"rtss", "none"})
        self.assertIsInstance(sample.detail, str)


class ImportTests(unittest.TestCase):
    def test_core_imports(self) -> None:
        from pingvault.services.admin import ADMIN_HELP, is_admin
        from pingvault.services.app_pause import AppPauseManager
        from pingvault.services.fps import FpsMonitor
        from pingvault.services.user_prefs import PrefsStore
        from pingvault.ui.main_window import MainWindow
        from pingvault.ui.tray import make_tray_icon

        self.assertTrue(callable(is_admin))
        self.assertTrue(ADMIN_HELP)
        self.assertTrue(callable(PrefsStore))
        self.assertTrue(callable(FpsMonitor))
        self.assertTrue(callable(AppPauseManager))
        self.assertTrue(callable(MainWindow))
        self.assertTrue(callable(make_tray_icon))


class SessionRestoreTests(unittest.TestCase):
    def test_restore_all_empty(self) -> None:
        from pingvault.services.session_restore import restore_all

        notes = restore_all()
        self.assertIsInstance(notes, list)


class AppPauseTests(unittest.TestCase):
    def test_resume_all_empty_is_fast(self) -> None:
        from pingvault.services.app_pause import AppPauseManager

        mgr = AppPauseManager(names=set())
        mgr._paused = []  # noqa: SLF001
        result = mgr.resume_all()
        self.assertEqual(result.resumed, ())
        self.assertIn("沒有需要恢復", result.message)


class StopBoostTests(unittest.TestCase):
    def test_mark_stop_makes_maintain_noop(self) -> None:
        from pingvault.services.optimizer import BoostStatus, Optimizer

        opt = Optimizer()
        opt.clear_stop()
        # Simulate an armed session without touching real processes.
        opt._active_game_id = "dummy"  # noqa: SLF001
        opt.mark_stop()
        self.assertIsNone(opt.maintain_boost())
        result = opt.stop_boost()
        self.assertEqual(result.status, BoostStatus.STOPPED)
        self.assertFalse(opt.is_active)

    def test_clear_stop_allows_new_session_flag(self) -> None:
        from pingvault.services.optimizer import Optimizer

        opt = Optimizer()
        opt.mark_stop()
        self.assertTrue(opt._aborted())  # noqa: SLF001
        opt.clear_stop()
        self.assertFalse(opt._aborted())  # noqa: SLF001


if __name__ == "__main__":
    unittest.main()
