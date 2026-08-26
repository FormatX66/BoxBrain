from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from web_deployment_branch import current_repository_plan, web_deployment_plan


class WebDeploymentBranchTests(unittest.TestCase):
    def receipt(self, **changes):
        value = {
            "schema": "aurum-web-static-mirror-receipt-v1",
            "state": "WEB_STATIC_MIRROR_OK",
            "source_commit": "0123456789abcdef",
            "observed_at": "2026-08-26T04:00:00+00:00",
            "hosted_deployment": {
                "configured": False,
                "missing": ["HOST", "USER", "KEY", "HOST_KEY", "REMOTE_PATH", "PUBLIC_URL"],
            },
            "verified": {
                "dashboard_truth_banner": True,
                "dashboard_reads_static_json": True,
                "plain_text_voice_status": True,
                "json_voice_status": True,
                "browser_static_voice_view": True,
                "seven_human_capabilities": True,
                "six_evidence_gates": True,
                "seeded_floor": "4/6",
            },
        }
        value.update(changes)
        return value

    def test_current_repository_receipt_is_a_real_zero_authority_consumer(self):
        repo_root = Path(__file__).resolve().parents[3]
        plan = current_repository_plan(repo_root)
        self.assertTrue(plan["source_receipt_path"].startswith("Projects/AurumBridge/results/web-static-mirror-"))
        self.assertEqual(plan["source_receipt_schema"], "aurum-web-static-mirror-receipt-v1")
        self.assertFalse(plan["external_action_allowed"])
        self.assertFalse(plan["deployment_promotion_allowed"])
        self.assertFalse(plan["authority_granted"])
        self.assertTrue(any(item["name"] == "revalidate-static-dashboard-sources" for item in plan["branches"]))

    def test_missing_hosted_configuration_is_a_boundary_not_a_deploy_action(self):
        plan = web_deployment_plan(
            self.receipt(),
            now=datetime(2026, 8, 26, 5, 0, tzinfo=timezone.utc),
        )
        boundary = next(item for item in plan["branches"] if item["name"] == "hosted-dashboard-configuration-boundary")
        self.assertEqual(boundary["disposition"], "wait-boundary")
        self.assertEqual(plan["verified_state"], "WEB_STATIC_MIRROR_OK")
        self.assertFalse(plan["hosted_deployment_configured"])
        self.assertFalse(plan["external_action_allowed"])

    def test_configured_hosted_candidate_can_be_validated_but_not_promoted(self):
        receipt = self.receipt(
            hosted_deployment={"configured": True, "missing": []},
        )
        plan = web_deployment_plan(
            receipt,
            now=datetime(2026, 8, 26, 5, 0, tzinfo=timezone.utc),
        )
        validate = next(item for item in plan["branches"] if item["name"] == "validate-hosted-dashboard-candidate")
        promote = next(item for item in plan["branches"] if item["name"] == "promote-hosted-dashboard")
        self.assertEqual(validate["disposition"], "prepare")
        self.assertEqual(promote["disposition"], "wait-boundary")
        self.assertTrue(promote["rollback_prepared"])
        self.assertFalse(plan["deployment_promotion_allowed"])

    def test_string_boolean_fails_closed(self):
        receipt = self.receipt(
            hosted_deployment={"configured": "false", "missing": []},
        )
        with self.assertRaises(ValueError):
            web_deployment_plan(receipt)

    def test_failed_static_mirror_does_not_become_verified_state(self):
        plan = web_deployment_plan(
            self.receipt(state="WEB_STATIC_MIRROR_FAILED"),
            now=datetime(2026, 8, 26, 5, 0, tzinfo=timezone.utc),
        )
        self.assertFalse(plan["static_mirror_verified"])
        self.assertEqual(plan["verified_state"], "WEB_STATIC_MIRROR_UNVERIFIED")
        self.assertFalse(plan["external_action_allowed"])


if __name__ == "__main__":
    unittest.main()
