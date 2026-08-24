from __future__ import annotations

import unittest

import triage


def healthy_snapshot():
    return {
        "boot_proof": {"schema": "aurum-boot-proof-v1"},
        "guardian": {"active": "A", "lkg": "A", "trial": None, "last_result": "steady"},
        "latest_regrow": None,
        "network": {
            "network_manager": {"returncode": 0, "output": "connected"},
            "default_route": {"returncode": 0, "output": "default via 192.0.2.1 dev eth0"},
        },
        "services": {"aurum-tinyseed.service": "active"},
    }


class TriageTests(unittest.TestCase):
    def test_missing_boot_proof_is_first_failure(self):
        snap = healthy_snapshot()
        snap["boot_proof"] = None
        self.assertEqual(triage.classify(snap)["code"], "BOOT_PROOF_MISSING")

    def test_invalid_guardian_stops_mutation(self):
        snap = healthy_snapshot()
        snap["guardian"] = {"active": "A", "lkg": None}
        self.assertEqual(triage.classify(snap)["code"], "GUARDIAN_STATE_INVALID")

    def test_network_failure_is_detected_before_regrow(self):
        snap = healthy_snapshot()
        snap["network"]["default_route"] = {"returncode": 0, "output": ""}
        self.assertEqual(triage.classify(snap)["code"], "NETWORK_NOT_READY")

    def test_inactive_setup_service_is_detected(self):
        snap = healthy_snapshot()
        snap["services"]["aurum-tinyseed.service"] = "failed"
        self.assertEqual(triage.classify(snap)["code"], "TINYSEED_SERVICE_NOT_ACTIVE")

    def test_incomplete_regrow_uses_saved_receipt(self):
        snap = healthy_snapshot()
        snap["latest_regrow"] = {"status": "refused"}
        self.assertEqual(triage.classify(snap)["code"], "REGROW_INCOMPLETE")

    def test_rollback_is_treated_as_protection_not_catastrophe(self):
        snap = healthy_snapshot()
        snap["guardian"]["last_result"] = "rolled-back:candidate-selftest-failed"
        self.assertEqual(triage.classify(snap)["code"], "CANDIDATE_ROLLED_BACK")

    def test_healthy_baseline_advances(self):
        self.assertEqual(triage.classify(healthy_snapshot())["code"], "BASELINE_HEALTHY")


if __name__ == "__main__":
    unittest.main()
