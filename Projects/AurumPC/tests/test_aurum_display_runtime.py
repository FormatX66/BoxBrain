from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "aurum_display_runtime.py"
SPEC = importlib.util.spec_from_file_location("aurum_display_runtime", MODULE_PATH)
assert SPEC and SPEC.loader
display_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = display_module
SPEC.loader.exec_module(display_module)
HopperDisplay = display_module.HopperDisplay


class HopperDisplayRuntimeTests(unittest.TestCase):
    def test_status_marks_pre_v2_running_echo_as_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            run = root / "run"
            state.mkdir()
            run.mkdir()
            policy = root / "policy.json"
            receipt = root / "receipt.json"
            game = root / "aurum_echo_native.py"
            game.write_text("# game\n", encoding="utf-8")
            policy.write_text(
                json.dumps(
                    {
                        "schema": "aurum-pc-autonomy-policy-v1",
                        "enabled": True,
                        "machine_display_name": "Hopper",
                        "machine_match": {
                            "installed_target_serial": "SERIAL",
                            "installed_target_size_bytes": 512,
                        },
                    }
                ),
                encoding="utf-8",
            )
            receipt.write_text(
                json.dumps({"target": {"serial": "SERIAL", "size_bytes": 512}}),
                encoding="utf-8",
            )
            (run / "echo-native.pid").write_text("123\n", encoding="utf-8")
            (state / "echo-native.json").write_text(
                json.dumps({"schema": "aurum.echo.native.v1", "status": "running"}),
                encoding="utf-8",
            )
            runtime = HopperDisplay(
                policy_path=policy,
                receipt_path=receipt,
                state_dir=state,
                run_dir=run,
                game=game,
            )
            with patch.object(runtime, "_owned", return_value=True):
                current = runtime.status()
            self.assertEqual(current["status"], "running")
            self.assertTrue(current["authorized"])
            self.assertFalse(current["game_schema_current"])

            (state / "echo-native.json").write_text(
                json.dumps({"schema": display_module.EXPECTED_GAME_SCHEMA, "status": "running"}),
                encoding="utf-8",
            )
            with patch.object(runtime, "_owned", return_value=True):
                upgraded = runtime.status()
            self.assertTrue(upgraded["game_schema_current"])

    def test_x_fallback_requires_libinput_driver_before_ready(self) -> None:
        runtime = HopperDisplay()

        def which(name: str):
            if name == "xinit":
                return "/usr/bin/xinit"
            if name == "Xorg":
                return "/usr/bin/Xorg"
            return None

        with (
            patch.object(display_module.shutil, "which", side_effect=which),
            patch.object(display_module, "_xorg_libinput_driver_available", return_value=False),
        ):
            missing = runtime._ensure_x_fallback({"install_local_display_dependencies": False})
        self.assertEqual(missing["status"], "missing")

        with (
            patch.object(display_module.shutil, "which", side_effect=which),
            patch.object(display_module, "_xorg_libinput_driver_available", return_value=True),
        ):
            ready = runtime._ensure_x_fallback({"install_local_display_dependencies": False})
        self.assertEqual(ready["status"], "ready")
        self.assertTrue(ready["libinput_driver"])


if __name__ == "__main__":
    unittest.main()
