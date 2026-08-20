from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "aurum_autonomy.py"
SPEC = importlib.util.spec_from_file_location("aurum_autonomy_tested", MODULE_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class AurumAutonomyPolicyTests(unittest.TestCase):
    def test_machine_authorization_is_bound_to_install_receipt(self) -> None:
        policy = {
            "schema": "aurum-pc-autonomy-policy-v1",
            "enabled": True,
            "machine_match": {
                "installed_target_serial": "SERIAL-1",
                "installed_target_size_bytes": 123456,
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / "aurum-installed.json"
            receipt.write_text(
                json.dumps({"target": {"serial": "SERIAL-1", "size_bytes": 123456}}),
                encoding="utf-8",
            )
            allowed, reason = module.machine_authorized(policy, receipt)
            self.assertTrue(allowed)
            self.assertEqual(reason, "authorized-machine-match")
            receipt.write_text(
                json.dumps({"target": {"serial": "OTHER", "size_bytes": 123456}}),
                encoding="utf-8",
            )
            allowed, reason = module.machine_authorized(policy, receipt)
            self.assertFalse(allowed)
            self.assertEqual(reason, "installed-target-serial-mismatch")

    def test_policy_does_not_enable_push_or_driver_swap(self) -> None:
        policy = json.loads((MODULE_PATH.with_name("pc01_autonomy_policy.json")).read_text(encoding="utf-8"))
        self.assertTrue(policy["enabled"])
        self.assertFalse(policy["driver_policy"]["load_synthesized_modules"])
        self.assertFalse(policy["driver_policy"]["replace_bound_drivers"])
        self.assertFalse(policy["driver_policy"]["firmware_writes"])
        self.assertFalse(policy["auto_reboot_after_runtime_update"])


if __name__ == "__main__":
    unittest.main()
