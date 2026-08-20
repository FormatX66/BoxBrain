from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "aurum_desktop_runtime.py"
SPEC = importlib.util.spec_from_file_location("aurum_desktop_runtime", MODULE_PATH)
assert SPEC and SPEC.loader
runtime_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runtime_module
SPEC.loader.exec_module(runtime_module)
HopperDesktopRuntime = runtime_module.HopperDesktopRuntime


class HopperDesktopRuntimeTests(unittest.TestCase):
    def test_status_is_machine_bound_and_reports_physical_surface(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            run = root / "run"
            state.mkdir()
            run.mkdir()
            policy = root / "policy.json"
            receipt = root / "receipt.json"
            desktop = root / "aurum_desktop.py"
            desktop.write_text("# desktop\n", encoding="utf-8")
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
            (run / "aurum-desktop.pid").write_text("123\n", encoding="utf-8")
            (state / "desktop-ui.json").write_text(
                json.dumps({"schema": "aurum.desktop.v1", "status": "running", "host_actuation": False}),
                encoding="utf-8",
            )
            runtime = HopperDesktopRuntime(
                policy_path=policy,
                receipt_path=receipt,
                state_dir=state,
                run_dir=run,
                desktop=desktop,
            )
            with patch.object(runtime, "_owned", return_value=True):
                current = runtime.status()
            self.assertTrue(current["authorized"])
            self.assertEqual(current["status"], "running")
            self.assertEqual(current["surface"], "physical")
            self.assertEqual(current["vt"], 2)
            self.assertFalse(current["host_actuation_api"])
            self.assertEqual(current["recovery_console"], "tty1")

    def test_wrong_machine_receipt_is_not_authorized(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            run = root / "run"
            state.mkdir()
            run.mkdir()
            policy = root / "policy.json"
            receipt = root / "receipt.json"
            desktop = root / "aurum_desktop.py"
            desktop.write_text("# desktop\n", encoding="utf-8")
            policy.write_text(
                json.dumps(
                    {
                        "schema": "aurum-pc-autonomy-policy-v1",
                        "enabled": True,
                        "machine_display_name": "Hopper",
                        "machine_match": {
                            "installed_target_serial": "EXPECTED",
                            "installed_target_size_bytes": 512,
                        },
                    }
                ),
                encoding="utf-8",
            )
            receipt.write_text(
                json.dumps({"target": {"serial": "OTHER", "size_bytes": 512}}),
                encoding="utf-8",
            )
            runtime = HopperDesktopRuntime(
                policy_path=policy,
                receipt_path=receipt,
                state_dir=state,
                run_dir=run,
                desktop=desktop,
            )
            authorized, reason = runtime.authorization()
            self.assertFalse(authorized)
            self.assertEqual(reason, "installed-target-serial-mismatch")

    def test_touchpad_detection_requires_pointer_style_input_block(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            devices = Path(temporary) / "devices"
            devices.write_text(
                "I: Bus=0011 Vendor=0002 Product=0007 Version=01b1\n"
                "N: Name=\"SynPS/2 Synaptics TouchPad\"\n"
                "H: Handlers=mouse0 event8\n\n"
                "N: Name=\"AT Translated Set 2 keyboard\"\n"
                "H: Handlers=sysrq kbd event3\n",
                encoding="utf-8",
            )
            self.assertTrue(runtime_module._touchpad_present(devices))
            devices.write_text(
                "N: Name=\"AT Translated Set 2 keyboard\"\n"
                "H: Handlers=sysrq kbd event3\n",
                encoding="utf-8",
            )
            self.assertFalse(runtime_module._touchpad_present(devices))


if __name__ == "__main__":
    unittest.main()
