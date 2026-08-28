from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
DESKTOP = ROOT / "aurum_desktop.py"
DESKTOP_RUNTIME = ROOT / "aurum_desktop_runtime.py"
GUI_RUNTIME = ROOT / "aurum_gui_runtime.py"
PROJECTION_RUNTIME = ROOT / "aurum_projection_runtime.py"
RUNTIME_UPDATE = ROOT / "aurum_runtime_update.py"
BUILD_ISO = ROOT / "build-iso.sh"


class AurumPhysicalDesktopContractTests(unittest.TestCase):
    def test_native_desktop_is_packaged_and_runtime_updatable(self) -> None:
        build = BUILD_ISO.read_text(encoding="utf-8")
        updater = RUNTIME_UPDATE.read_text(encoding="utf-8")
        for name in ("aurum_desktop.py", "aurum_desktop_runtime.py"):
            self.assertIn(name, build)
            self.assertIn(name, updater)

    def test_physical_launcher_preserves_recovery_and_has_two_display_paths(self) -> None:
        launcher = DESKTOP_RUNTIME.read_text(encoding="utf-8")
        self.assertIn('"surface": "physical"', launcher)
        self.assertIn('"vt": 2', launcher)
        self.assertIn('"recovery_console": "tty1"', launcher)
        self.assertIn('SDL_VIDEODRIVER=kmsdrm', launcher)
        self.assertIn('SDL_VIDEODRIVER=x11', launcher)
        self.assertIn('"host_actuation_api": False', launcher)
        self.assertIn('"vt2-owned-by-echo"', launcher)

    def test_desktop_only_reports_running_after_fullscreen_display_exists(self) -> None:
        desktop = DESKTOP.read_text(encoding="utf-8")
        display = desktop.index("pygame.display.set_mode")
        running = desktop.index('"status": "running"', display)
        self.assertGreater(running, display)
        self.assertIn("pygame.FULLSCREEN", desktop)
        self.assertIn("Ctrl+Alt+F1", desktop)
        self.assertIn('"host_actuation": "bounded-confirmed-actions"', desktop)
        self.assertIn("RECOVERY CONSOLE", desktop)
        self.assertIn("bounded-console", desktop)
        self.assertIn("aurum.gui-recovery-console.bounded.v1", desktop)

    def test_gui_start_calls_physical_desktop_runtime(self) -> None:
        gui = GUI_RUNTIME.read_text(encoding="utf-8")
        self.assertIn('self._desktop("start")', gui)
        self.assertIn('self._desktop("status")', gui)
        self.assertIn('"physical_desktop"', gui)

    def test_html_projection_refuses_to_claim_ready_without_keyboard_pointer_libinput(self) -> None:
        projection = PROJECTION_RUNTIME.read_text(encoding="utf-8")
        self.assertIn("_xorg_libinput_ready", projection)
        self.assertIn("_ensure_input_path", projection)
        self.assertIn('current.get("keyboard_ready") is True', projection)
        self.assertIn('current.get("pointer_ready") is True', projection)
        self.assertIn('current.get("xorg_event_path_ready") is True', projection)


if __name__ == "__main__":
    unittest.main()
