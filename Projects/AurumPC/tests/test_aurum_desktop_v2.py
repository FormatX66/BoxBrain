from __future__ import annotations

import importlib.util
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
DESKTOP = ROOT / "aurum_desktop.py"
TIME = ROOT / "aurum_time.py"


def load_desktop():
    spec = importlib.util.spec_from_file_location("aurum_desktop_test", DESKTOP)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AurumDesktopV2Tests(unittest.TestCase):
    def test_click_targets_survive_until_event_processing(self) -> None:
        source = DESKTOP.read_text(encoding="utf-8")
        event_at = source.index("for event in pygame.event.get():")
        clear_at = source.index("click_targets.clear()", event_at)
        mouse_at = source.index("pygame.MOUSEBUTTONUP", event_at)
        self.assertLess(mouse_at, clear_at)

    def test_old_decorative_hardware_percentages_are_gone(self) -> None:
        source = DESKTOP.read_text(encoding="utf-8")
        self.assertNotIn('(\"CPU\",32)', source.replace(" ", ""))
        self.assertNotIn('(\"Memory\",68)', source.replace(" ", ""))
        self.assertNotIn('(\"Storage\",46)', source.replace(" ", ""))
        self.assertNotIn('(\"GPU\",24)', source.replace(" ", ""))
        for helper in ("_cpu_percent", "_memory_percent", "_storage_percent", "_gpu_percent"):
            self.assertIn(f"def {helper}", source)

    def test_missing_state_is_not_promoted_to_ready(self) -> None:
        source = DESKTOP.read_text(encoding="utf-8")
        self.assertIn('runtime_state.get("status") or "unknown"', source)
        self.assertIn('autonomy.get("status") or "unknown"', source)
        self.assertIn('driver.get("status") or "unknown"', source)

    def test_time_surface_requires_ntp_evidence(self) -> None:
        desktop_source = DESKTOP.read_text(encoding="utf-8")
        time_source = TIME.read_text(encoding="utf-8")
        self.assertIn('"NTP" if time_state.get("synchronized") else "LOCAL"', desktop_source)
        self.assertIn("Synchronize From Time Server", desktop_source)
        self.assertIn("ServerName", time_source)
        self.assertIn("ServerAddress", time_source)
        self.assertIn('"authoritative": synchronized', time_source)

    def test_health_flags_unsynchronized_time(self) -> None:
        module = load_desktop()
        label, issues = module._system_health(
            {
                "online": True,
                "pointers": 1,
                "battery": {"present": True, "percent": 50, "charging": True},
                "time": {"synchronized": False},
            }
        )
        self.assertEqual(label, "Attention")
        self.assertIn("time not server-synchronized", issues)


if __name__ == "__main__":
    unittest.main()
