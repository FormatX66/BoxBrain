from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from aurum_driver_codelation_bridge import DriverCodelationBridge


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class DriverCodelationBridgeTests(unittest.TestCase):
    def test_exact_pc_evidence_reconciles_without_actuation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / "driver-lab"
            device_dir = state / "devices" / "wifi-test"
            device_dir.mkdir(parents=True)
            model_path = device_dir / "model.json"
            model_path.write_text(
                json.dumps(
                    {
                        "device_id": "wifi-test",
                        "identity": {
                            "collection": "network_interfaces",
                            "name": "wlp6s0",
                            "driver": "iwlwifi",
                            "modalias": "pci:test",
                            "carrier": "1",
                            "operstate": "up",
                            "mtu": "1500",
                        },
                        "bound_driver": "iwlwifi",
                        "module": {"available": True, "driver": "iwlwifi"},
                        "latest_observation": {
                            "read_only": True,
                            "network": {"carrier": "1", "operstate": "up", "mtu": "1500"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            (state / "latest-cycle.json").write_text(
                json.dumps(
                    {
                        "queue": [
                            {
                                "device_id": "wifi-test",
                                "risk_class": "network",
                                "gated": False,
                                "model": str(model_path),
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            result = DriverCodelationBridge(workspace=REPOSITORY_ROOT, state_dir=state).cycle()
            self.assertEqual(result["status"], "cycle-complete")
            self.assertEqual(result["devices_reconciled"], 1)
            self.assertGreaterEqual(result["verified_claims"], 4)
            self.assertFalse(result["physical_write_authorized"])
            device = result["devices"][0]
            self.assertEqual(device["trace_status"], "passed")
            self.assertTrue(device["physical_hardware_proof"])
            self.assertFalse(device["physical_write_authorized"])


if __name__ == "__main__":
    unittest.main()
