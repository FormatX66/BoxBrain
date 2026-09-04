from __future__ import annotations

import ast
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
    def test_current_desktop_receipt_is_recognized_only_with_owned_process(self) -> None:
        desktop_source = MODULE_PATH.with_name("aurum_desktop.py")
        declarations = ast.parse(desktop_source.read_text(encoding="utf-8")).body
        current_schema = next(
            ast.literal_eval(node.value)
            for node in declarations
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "SCHEMA" for target in node.targets)
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = HopperDesktopRuntime(
                policy_path=root / "policy.json",
                receipt_path=root / "installed.json",
                state_dir=root,
                run_dir=root,
                desktop=desktop_source,
            )
            for schema, owned, expected in (
                (current_schema, True, "running"),
                ("aurum.desktop.v1", True, "running"),
                (current_schema, False, "stopped"),
                ("unrecognized-desktop", True, "stopped"),
            ):
                with self.subTest(schema=schema, owned=owned):
                    runtime.desktop_receipt.write_text(
                        json.dumps({"schema": schema, "status": "running", "pid": 123}),
                        encoding="utf-8",
                    )
                    with (
                        patch.object(runtime, "authorization", return_value=(True, "test")),
                        patch.object(runtime, "_pid", return_value=123),
                        patch.object(runtime, "_owned", return_value=owned),
                    ):
                        self.assertEqual(runtime.status()["status"], expected)

    def test_generic_installed_aurum_pc_is_authorized_by_exact_receipt(self) -> None:
        authorized, reason = runtime_module._authorized(
            {
                "schema": "aurum-pc-autonomy-policy-v1",
                "enabled": True,
                "machine_display_name": "Aurum PC",
                "machine_match": {
                    "installed_target_serial": "GENERIC-SERIAL",
                    "installed_target_size_bytes": 256,
                },
            },
            {"target": {"serial": "GENERIC-SERIAL", "size_bytes": 256}},
        )
        self.assertTrue(authorized)
        self.assertEqual(reason, "authorized-aurum-pc")

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
