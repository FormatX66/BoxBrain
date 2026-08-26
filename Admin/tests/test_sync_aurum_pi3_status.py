from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from Admin.sync_aurum_pi3_status import Pi3StatusError, sync_pi3_status


class SyncAurumPi3StatusTests(unittest.TestCase):
    def root(self) -> Path:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "Projects/Aurum").mkdir(parents=True)
        (root / "Projects/AdaptiveDrivers/evidence").mkdir(parents=True)
        plan = {
            "schema": "aurum-completion-plan-v1",
            "gates": [
                {
                    "id": "adaptive-kernel-independent",
                    "lane": "experiment",
                    "depends_on": [],
                    "state": "ci-passed-experiment",
                    "ready_now": True,
                    "proof": "bounded candidate plan",
                },
                {
                    "id": "pi3-kernel-canary",
                    "lane": "physical-experiment",
                    "depends_on": ["pi-physical-boot", "adaptive-kernel-independent"],
                    "state": "blocked-on-physical-hardware",
                    "ready_now": False,
                    "proof": "old stale blocker",
                },
            ],
        }
        (root / "Projects/Aurum/completion-plan.json").write_text(json.dumps(plan), encoding="utf-8")
        return root

    def generation2(self) -> dict:
        return {
            "schema": "aurum.pi3.adaptive-driver.generation2.physical.v1",
            "state": "passed-physical-userspace-generation2",
            "target": {"serial": "00000000a6a7df7f", "strict_key_only_ssh": True},
            "generation2": {
                "candidate_id": "pi3-net-sysfs-tolerant-v2",
                "generation": 2,
                "decision": "promoted",
                "score": 100.0,
                "read_evidence_complete": True,
                "lkg_preserved_during_test": True,
            },
            "fault_injection": {
                "candidate_id": "pi3-net-sysfs-tolerant-v2-missing-field-fixture",
                "decision": "quarantined",
                "reason": "required-read-only-field-unavailable",
                "missing_fields": ["carrier"],
                "lkg_preserved_during_test": True,
                "lkg_sha256_before": "abc",
                "lkg_sha256_after": "abc",
            },
            "isolated_metadata_rollback": {"restored_profile_id": "pi3-linux-reference-driver", "passed": True},
            "safety": {
                "system_driver_changed": False,
                "kernel_module_loaded": False,
                "kernel_driver_binding_changed": False,
                "firmware_mutation_allowed": False,
                "kernel_driver_mutation_allowed": False,
                "production_nodes_allowed": False,
                "persistent_trust_changed": False,
            },
        }

    def write_generation2(self, root: Path, value: dict | None = None) -> None:
        path = root / "Projects/AdaptiveDrivers/evidence/pi3-generation2-physical.json"
        path.write_text(json.dumps(value or self.generation2()), encoding="utf-8")

    def test_generation2_removes_stale_physical_hardware_blocker_without_granting_kernel_authority(self):
        root = self.root()
        self.write_generation2(root)
        result = sync_pi3_status(root)
        self.assertTrue(result["changed"])
        plan = json.loads((root / "Projects/Aurum/completion-plan.json").read_text())
        by_id = {item["id"]: item for item in plan["gates"]}
        self.assertEqual(by_id["pi3-physical-baseline"]["state"], "passed-physical-experiment")
        self.assertEqual(by_id["pi3-adaptive-driver-userspace-generation2"]["state"], "passed-physical-experiment")
        kernel = by_id["pi3-kernel-canary"]
        self.assertEqual(kernel["state"], "held-on-kernel-mutation-prerequisites")
        self.assertFalse(kernel["ready_now"])
        self.assertNotIn("pi-physical-boot", kernel["depends_on"])
        self.assertIn("pi3-adaptive-driver-userspace-generation2", kernel["depends_on"])

    def test_generation2_fails_closed_if_system_driver_changed(self):
        root = self.root()
        evidence = self.generation2()
        evidence["safety"]["system_driver_changed"] = True
        self.write_generation2(root, evidence)
        before = (root / "Projects/Aurum/completion-plan.json").read_text()
        with self.assertRaises(Pi3StatusError):
            sync_pi3_status(root)
        self.assertEqual((root / "Projects/Aurum/completion-plan.json").read_text(), before)

    def test_kernel_preflight_projects_technical_hold_but_never_ready_now(self):
        root = self.root()
        self.write_generation2(root)
        preflight = {
            "schema": "aurum.pi3.kernel-canary.preflight.v1",
            "state": "held-out-of-band-watchdog-unproven",
            "target": {"serial": "00000000a6a7df7f", "strict_key_only_ssh": True},
            "authority": {
                "kernel_module_load_allowed": False,
                "driver_binding_change_allowed": False,
                "firmware_mutation_allowed": False,
            },
            "safety": {"module_loaded": False, "system_driver_changed": False, "production_nodes_allowed": False},
            "next_gate": "prove-automatic-out-of-band-watchdog-and-recovery",
        }
        path = root / "Projects/AdaptiveDrivers/evidence/pi3-kernel-canary-preflight.json"
        path.write_text(json.dumps(preflight), encoding="utf-8")
        result = sync_pi3_status(root)
        self.assertEqual(result["kernel_state"], "held-out-of-band-watchdog-unproven")
        plan = json.loads((root / "Projects/Aurum/completion-plan.json").read_text())
        kernel = next(item for item in plan["gates"] if item["id"] == "pi3-kernel-canary")
        self.assertFalse(kernel["ready_now"])
        self.assertIn("out-of-band-watchdog", kernel["state"])


if __name__ == "__main__":
    unittest.main()
