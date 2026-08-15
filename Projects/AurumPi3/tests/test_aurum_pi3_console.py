from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

import aurum_pi3_console as console


class AurumPi3ConsoleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state_path = Path(self.temporary.name) / "capability-state.json"
        self.store = console.StateStore(self.state_path)
        self.store.ensure_initialized()

    def test_inventory_distinguishes_discovery_verification_and_authorization(self) -> None:
        inventory = console.capability_inventory(self.store)["inventory"]
        by_name = {item["name"]: item for item in inventory}
        self.assertTrue(by_name["capabilities"]["discovered"])
        self.assertTrue(by_name["capabilities"]["verified"])
        self.assertTrue(by_name["capabilities"]["authorized"])
        self.assertFalse(by_name["network"]["verified"])
        self.assertFalse(by_name["reboot"]["authorized"])
        self.assertEqual(by_name["update"]["kind"], "action")
        self.assertEqual(by_name["rollback"]["kind"], "action")
        self.assertNotIn("upgrade.apply", by_name)

    def test_verified_probe_is_persisted_and_observable(self) -> None:
        with mock.patch.dict(
            console.PROBES,
            {"network": lambda: ({"interfaces": [{"name": "eth0"}]}, {"interfaces": 1})},
        ):
            result = console.run_probe("network", self.store)
        self.assertTrue(result.ok)
        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
        network = persisted["capabilities"]["network"]
        self.assertTrue(network["discovered"])
        self.assertTrue(network["verified"])
        self.assertTrue(network["authorized"])
        self.assertEqual(network["summary"]["interfaces"], 1)
        self.assertEqual(console.observe(self.store, "network")["state"]["status"], "verified")

    def test_failed_probe_is_a_local_barrier_and_rescan_continues(self) -> None:
        def unavailable() -> tuple[dict, dict]:
            raise console.LocalBarrier("usb-test-unavailable")

        with mock.patch.dict(
            console.PROBES,
            {
                "usb": unavailable,
                "network": lambda: ({"interfaces": []}, {"interfaces": 0}),
            },
        ), mock.patch.object(console, "PROBE_ORDER", ("usb", "network")):
            result = console.rescan(self.store)
        self.assertFalse(result["ok"])
        self.assertTrue(result["continuation_allowed"])
        self.assertEqual(len(result["results"]), 2)
        self.assertFalse(result["results"][0]["verified"])
        self.assertTrue(result["results"][1]["verified"])
        self.assertEqual(result["barriers"][0]["scope"], "usb")

    def test_frontier_selects_only_the_next_local_gap(self) -> None:
        self.store.record_probe(
            "hardware", discovered=True, verified=True, summary={}, barrier=None
        )
        result = console.frontier(self.store)
        self.assertEqual(result["next_gap"], "network")
        self.assertEqual(result["suggested_command"], "rescan network")

    def test_power_action_requires_exact_confirmation(self) -> None:
        with mock.patch.object(console.subprocess, "run") as run:
            result = console.explicit_power("reboot", None)
        self.assertFalse(result["authorized"])
        self.assertFalse(result["performed"])
        run.assert_not_called()

    def test_unknown_command_never_becomes_shell_execution(self) -> None:
        with mock.patch.object(console.subprocess, "run") as run:
            result = console.execute(["echo", "unsafe"], self.store)
        self.assertFalse(result["ok"])
        self.assertTrue(result["continuation_allowed"])
        run.assert_not_called()
        source = (PROJECT / "aurum_pi3_console.py").read_text(encoding="utf-8")
        self.assertNotIn("shell=True", source)
        self.assertNotIn("os.system", source)

    def test_network_update_requires_exact_authorization_token(self) -> None:
        result = console.execute(
            ["update", "https://example.invalid/manifest.json", "0" * 64, "yes"],
            self.store,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["barrier"]["reason"], "network-authorization-token-invalid")

    def test_rollback_requires_exact_confirmation(self) -> None:
        with mock.patch.object(console, "_run_updater") as updater:
            result = console.execute(["rollback"], self.store)
        self.assertFalse(result["ok"])
        updater.assert_not_called()

    def test_json_mode_emits_one_parseable_document(self) -> None:
        environment = {
            "AURUM_CAPABILITY_STATE": str(Path(self.temporary.name) / "cli-state.json")
        }
        completed = subprocess.run(
            [sys.executable, str(PROJECT / "aurum_pi3_console.py"), "--json", "capabilities"],
            check=True,
            capture_output=True,
            text=True,
            env={**__import__("os").environ, **environment},
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["capability"], "capabilities")
        self.assertEqual(completed.stdout.count("\n"), 1)


if __name__ == "__main__":
    unittest.main()
