from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Projects.AurumPC.aurum_boot_screen import BootScreen


class AurumBootScreenTests(unittest.TestCase):
    def test_disabled_screen_records_progress_without_terminal_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = io.StringIO()
            state = Path(temporary) / "boot-screen.json"
            screen = BootScreen(output=output, state_path=state, enabled=False)
            screen.update("hardware", "ready", "4 input devices")
            screen.update("input", "degraded", "receipt unavailable")
            screen.finish("degraded")

            payload = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "aurum.boot-screen.v1")
            self.assertEqual(payload["status"], "degraded")
            self.assertEqual(payload["stages"][0]["status"], "ready")
            self.assertEqual(output.getvalue(), "")

    def test_enabled_screen_renders_branded_hopper_progress(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = io.StringIO()
            with patch.dict(os.environ, {"AURUM_SHOW_BOOT_DIAGNOSTICS": "1"}):
                screen = BootScreen(
                    output=output,
                    state_path=Path(temporary) / "boot-screen.json",
                    enabled=True,
                )
                screen.update("desktop", "active")
                screen.finish("ready", "Hopper desktop is ready")
            rendered = output.getvalue()
            self.assertIn("A U R U M", rendered)
            self.assertIn("Hopper recovery status", rendered)
            self.assertIn("READY", rendered)


if __name__ == "__main__":
    unittest.main()
