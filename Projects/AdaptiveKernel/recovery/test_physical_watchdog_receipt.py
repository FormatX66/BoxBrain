from __future__ import annotations

import copy
import unittest

from Projects.AdaptiveKernel.recovery.physical_watchdog_receipt import (
    PhysicalWatchdogReceiptError,
    evaluate_physical_receipt,
)


class PhysicalWatchdogReceiptTests(unittest.TestCase):
    def receipt(self) -> dict:
        def component(role: str) -> dict:
            value = {
                "component_id": f"pi4-{role}",
                "role": role,
                "identity_fingerprint": f"SHA256:{role}-identity",
                "independently_identified": True,
                "independent_of_target_kernel": True,
                "simulation_only": False,
            }
            if role == "observer":
                value["signal_path"] = "hdmi-capture"
            if role == "actuator":
                value["can_control_power"] = True
                value["can_select_or_restore_lkg"] = True
            return value

        def ref(kind: str, digit: str) -> dict:
            return {"kind": kind, "locator": f"artifact:{kind}", "sha256": digit * 64}

        target = {
            "model_marker": "Raspberry Pi 3 Model B Rev 1.2",
            "serial": "00000000a6a7df7f",
        }
        lkg = {"artifact_id": "pi3-current-card-lkg", "sha256": "a" * 64}
        return {
            "schema": "aurum.pi3.oob-recovery.physical.v1",
            "mode": "physical",
            "state": "verified-physical-recovery",
            "target_expected": target,
            "lkg_expected": lkg,
            "topology": {role: component(role) for role in ("controller", "observer", "actuator", "verifier")},
            "observation": {
                "failure_detected": True,
                "automatic_detection": True,
                "target_kernel_responsive": False,
                "local_target_timer_only": False,
                "evidence_refs": [ref("hdmi-failure-frame", "1")],
            },
            "actuation": {
                "requested": True,
                "completed": True,
                "automatic": True,
                "power_control_exercised": True,
                "lkg_recovery_exercised": True,
                "network_only": False,
                "evidence_refs": [ref("power-lkg-cycle", "2")],
            },
            "post_recovery": {
                "target": copy.deepcopy(target),
                "lkg": copy.deepcopy(lkg),
                "healthy": True,
                "evidence_refs": [ref("identity-lkg-health", "3")],
            },
            "provenance": {
                "source_commit": "b" * 40,
                "collector_id": "pi4-oob-controller",
                "collector_sha256": "c" * 64,
                "run_id": "12345",
            },
            "authority": {
                "mutation_authority_granted": False,
                "kernel_module_load_allowed": False,
                "driver_binding_change_allowed": False,
                "firmware_mutation_allowed": False,
            },
            "safety": {"production_nodes_allowed": False},
        }

    def test_complete_physical_receipt_proves_watchdog_but_not_kernel_authority(self):
        result = evaluate_physical_receipt(self.receipt())
        self.assertEqual(result["state"], "out-of-band-watchdog-proven")
        self.assertTrue(result["watchdog_proven"])
        self.assertFalse(result["mutation_authority_granted"])
        self.assertTrue(result["physical_proof_validated"])
        self.assertFalse(result["physical_proof_inferred"])

    def test_network_only_actuation_is_refused(self):
        receipt = self.receipt()
        receipt["actuation"]["network_only"] = True
        with self.assertRaises(PhysicalWatchdogReceiptError):
            evaluate_physical_receipt(receipt)

    def test_local_target_timer_is_refused(self):
        receipt = self.receipt()
        receipt["observation"]["local_target_timer_only"] = True
        with self.assertRaises(PhysicalWatchdogReceiptError):
            evaluate_physical_receipt(receipt)

    def test_wrong_target_or_lkg_is_refused(self):
        for mutate in (
            lambda value: value["post_recovery"]["target"].update(serial="0000000000000000"),
            lambda value: value["post_recovery"]["lkg"].update(sha256="d" * 64),
        ):
            with self.subTest(mutate=mutate):
                receipt = self.receipt()
                mutate(receipt)
                with self.assertRaises(PhysicalWatchdogReceiptError):
                    evaluate_physical_receipt(receipt)

    def test_identity_collision_or_simulation_component_is_refused(self):
        receipt = self.receipt()
        receipt["topology"]["actuator"]["component_id"] = receipt["topology"]["observer"]["component_id"]
        with self.assertRaises(PhysicalWatchdogReceiptError):
            evaluate_physical_receipt(receipt)
        receipt = self.receipt()
        receipt["topology"]["observer"]["simulation_only"] = True
        with self.assertRaises(PhysicalWatchdogReceiptError):
            evaluate_physical_receipt(receipt)

    def test_authority_smuggling_is_refused(self):
        receipt = self.receipt()
        receipt["authority"]["mutation_authority_granted"] = True
        with self.assertRaises(PhysicalWatchdogReceiptError):
            evaluate_physical_receipt(receipt)

    def test_evidence_requires_distinct_content_hashes_and_provenance(self):
        receipt = self.receipt()
        receipt["actuation"]["evidence_refs"][0]["sha256"] = "1" * 64
        with self.assertRaises(PhysicalWatchdogReceiptError):
            evaluate_physical_receipt(receipt)
        receipt = self.receipt()
        receipt["provenance"]["source_commit"] = "not-a-commit"
        with self.assertRaises(PhysicalWatchdogReceiptError):
            evaluate_physical_receipt(receipt)


if __name__ == "__main__":
    unittest.main()
