import json
from pathlib import Path
import tempfile
import unittest

from Projects.AdaptiveDrivers.adaptive_driver_loop import (
    DriverCandidate,
    build_capability_model,
    candidate_catalog,
    collect_hardware_fingerprint,
    gate_pi3_fingerprint,
    provision_pi3_fixture,
    rank_candidates,
    rollback_to_previous,
    run_adaptive_driver_loop,
)


class AdaptiveDriverLoopTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.fixture_root = self.base / "fixture-root"
        self.overrides = provision_pi3_fixture(self.fixture_root)
        self.state_dir = self.base / "state"

    def test_pi3_fingerprint_and_capability_model(self):
        fingerprint = collect_hardware_fingerprint(
            self.fixture_root, platform_overrides=self.overrides
        )
        self.assertTrue(gate_pi3_fingerprint(fingerprint)["accepted"])
        capability = build_capability_model(fingerprint)
        self.assertEqual(capability["target_interface"], "eth0")
        self.assertTrue(capability["capabilities"]["read-packet-counters"]["supported"])
        self.assertEqual(capability["write_capabilities"], [])

    def test_end_to_end_promotes_metadata_and_preserves_rollback(self):
        result = run_adaptive_driver_loop(
            self.state_dir,
            root=self.fixture_root,
            platform_overrides=self.overrides,
            allow_promotion=True,
            run_id="test-promote",
        )
        self.assertEqual(result["decision"], "promoted")
        self.assertEqual(result["score"]["score"], 100.0)
        self.assertTrue(result["lkg_preserved_during_test"])
        self.assertFalse(result["system_driver_changed"])
        self.assertFalse(result["test"]["kernel_module_loaded"])
        lkg = json.loads((self.state_dir / "lkg.json").read_text(encoding="utf-8"))
        self.assertEqual(lkg["active"]["profile_id"], "pi3-net-sysfs-strict-v1")
        snapshot = self.state_dir / lkg["rollback"]["snapshot"]
        self.assertTrue(snapshot.is_file())

    def test_generation_2_tolerant_candidate_promotes_with_complete_evidence(self):
        result = run_adaptive_driver_loop(
            self.state_dir,
            root=self.fixture_root,
            platform_overrides=self.overrides,
            allow_promotion=True,
            requested_candidate="pi3-net-sysfs-tolerant-v2",
            run_id="test-generation-2-promote",
        )
        self.assertEqual(result["decision"], "promoted")
        self.assertEqual(result["candidate"]["generation"], 2)
        self.assertEqual(result["score"]["score"], 100.0)
        self.assertTrue(result["test"]["read_evidence_complete"])
        self.assertEqual(result["test"]["missing_fields"], [])
        self.assertFalse(result["test"]["kernel_module_loaded"])
        self.assertFalse(result["test"]["kernel_driver_binding_changed"])
        lkg = json.loads((self.state_dir / "lkg.json").read_text(encoding="utf-8"))
        self.assertEqual(lkg["active"]["profile_id"], "pi3-net-sysfs-tolerant-v2")
        self.assertEqual(lkg["active"]["generation"], 2)
        self.assertEqual(
            lkg["active"]["kind"],
            "generation-2-userspace-hardware-specific-observer",
        )
        self.assertFalse(lkg["system_driver_changed"])

    def test_missing_sysfs_field_is_quarantined_and_preserves_generation_2_lkg(self):
        promoted = run_adaptive_driver_loop(
            self.state_dir,
            root=self.fixture_root,
            platform_overrides=self.overrides,
            allow_promotion=True,
            requested_candidate="pi3-net-sysfs-tolerant-v2",
            run_id="test-generation-2-before-fault",
        )
        self.assertEqual(promoted["decision"], "promoted")
        prior_lkg = (self.state_dir / "lkg.json").read_bytes()

        result = run_adaptive_driver_loop(
            self.state_dir,
            root=self.fixture_root,
            platform_overrides=self.overrides,
            allow_promotion=True,
            requested_candidate=(
                "pi3-net-sysfs-tolerant-v2-missing-field-fixture"
            ),
            include_faults=True,
            run_id="test-generation-2-missing-field",
        )

        self.assertEqual(result["decision"], "quarantined")
        self.assertEqual(result["reason"], "required-read-only-field-unavailable")
        self.assertEqual(result["candidate"]["generation"], 2)
        self.assertEqual(result["test"]["missing_fields"], ["carrier"])
        self.assertFalse(result["test"]["read_evidence_complete"])
        self.assertTrue(result["lkg_preserved_during_test"])
        self.assertEqual((self.state_dir / "lkg.json").read_bytes(), prior_lkg)
        self.assertEqual(
            result["lkg"]["active_after"], "pi3-net-sysfs-tolerant-v2"
        )
        self.assertFalse(result["system_driver_changed"])
        self.assertFalse(result["test"]["kernel_module_loaded"])
        self.assertFalse(result["test"]["kernel_driver_binding_changed"])
        self.assertEqual(
            (self.fixture_root / "sys/class/net/eth0/carrier").read_text(
                encoding="utf-8"
            ),
            "1\n",
        )
        fault_branch = next(
            branch
            for branch in result["future_branches"]
            if branch["branch_id"] == "missing-sysfs-field-fault-injection"
        )
        self.assertEqual(fault_branch["status"], "quarantined")
        self.assertIn("preserved LKG", fault_branch["verification"])

    def test_rollback_restores_reference_lkg(self):
        run_adaptive_driver_loop(
            self.state_dir,
            root=self.fixture_root,
            platform_overrides=self.overrides,
            allow_promotion=True,
            run_id="test-rollback",
        )
        restored = rollback_to_previous(self.state_dir)
        self.assertEqual(restored["active"]["profile_id"], "pi3-linux-reference-driver")
        current = json.loads((self.state_dir / "lkg.json").read_text(encoding="utf-8"))
        self.assertEqual(current, restored)

    def test_lower_coverage_candidate_is_rejected_and_lkg_stays_reference(self):
        result = run_adaptive_driver_loop(
            self.state_dir,
            root=self.fixture_root,
            platform_overrides=self.overrides,
            allow_promotion=True,
            requested_candidate="pi3-net-sysfs-minimal-v1",
            run_id="test-reject",
        )
        self.assertEqual(result["decision"], "rejected")
        self.assertLess(result["score"]["score"], result["score"]["baseline_score"])
        lkg = json.loads((self.state_dir / "lkg.json").read_text(encoding="utf-8"))
        self.assertEqual(lkg["active"]["profile_id"], "pi3-linux-reference-driver")

    def test_behavior_mismatch_is_rejected(self):
        result = run_adaptive_driver_loop(
            self.state_dir,
            root=self.fixture_root,
            platform_overrides=self.overrides,
            allow_promotion=True,
            requested_candidate="pi3-net-sysfs-mismatch-fixture",
            include_faults=True,
            run_id="test-mismatch",
        )
        self.assertEqual(result["decision"], "rejected")
        self.assertFalse(result["score"]["functional_match"])

    def test_build_failure_is_quarantined_without_lkg_change(self):
        result = run_adaptive_driver_loop(
            self.state_dir,
            root=self.fixture_root,
            platform_overrides=self.overrides,
            allow_promotion=True,
            requested_candidate="pi3-net-sysfs-build-failure-fixture",
            include_faults=True,
            run_id="test-quarantine",
        )
        self.assertEqual(result["decision"], "quarantined")
        self.assertTrue(result["lkg_preserved"])

    def test_non_pi3_is_held_before_candidate_build(self):
        overrides = {**self.overrides, "model": "Raspberry Pi 4 Model B"}
        result = run_adaptive_driver_loop(
            self.state_dir,
            root=self.fixture_root,
            platform_overrides=overrides,
            allow_promotion=True,
            run_id="test-gate",
        )
        self.assertEqual(result["state"], "waiting")
        self.assertEqual(result["decision"], "quarantined")
        self.assertFalse((self.state_dir / "lkg.json").exists())

    def test_boot_change_keeps_same_hardware_fingerprint(self):
        first = collect_hardware_fingerprint(
            self.fixture_root, platform_overrides=self.overrides
        )
        second = collect_hardware_fingerprint(
            self.fixture_root,
            platform_overrides={**self.overrides, "boot_id": "new-clean-boot-id"},
        )
        self.assertNotEqual(first["boot_id"], second["boot_id"])
        self.assertEqual(first["fingerprint_sha256"], second["fingerprint_sha256"])

    def test_kernel_change_quarantines_and_preserves_prior_lkg(self):
        first = run_adaptive_driver_loop(
            self.state_dir,
            root=self.fixture_root,
            platform_overrides=self.overrides,
            allow_promotion=True,
            run_id="test-before-kernel-change",
        )
        prior_lkg = (self.state_dir / "lkg.json").read_bytes()
        changed = run_adaptive_driver_loop(
            self.state_dir,
            root=self.fixture_root,
            platform_overrides={**self.overrides, "kernel": "6.7.0-v7+"},
            allow_promotion=True,
            run_id="test-after-kernel-change",
        )
        self.assertEqual(first["decision"], "promoted")
        self.assertEqual(changed["decision"], "quarantined")
        self.assertEqual(changed["reason"], "hardware-or-kernel-fingerprint-changed")
        self.assertEqual((self.state_dir / "lkg.json").read_bytes(), prior_lkg)

    def test_qpu_is_skipped_for_small_candidate_space(self):
        ordered, evidence = rank_candidates(
            candidate_catalog(), qpu_command="unavailable-qpu-provider"
        )
        self.assertEqual(ordered[0].candidate_id, "pi3-net-sysfs-strict-v1")
        self.assertFalse(evidence["qpu_used"])
        self.assertEqual(evidence["qpu_reason"], "candidate-space-too-small")

    def test_invalid_qpu_provider_falls_back_classically(self):
        candidates = tuple(
            DriverCandidate(f"candidate-{index}", 1, ("mtu",), True, 0.5)
            for index in range(8)
        )
        ordered, evidence = rank_candidates(
            candidates, qpu_command="definitely-not-an-installed-qpu-command"
        )
        self.assertEqual(len(ordered), 8)
        self.assertFalse(evidence["qpu_used"])
        self.assertTrue(evidence["classical_fallback"])
        self.assertIn("provider-error", evidence["qpu_reason"])


if __name__ == "__main__":
    unittest.main()
