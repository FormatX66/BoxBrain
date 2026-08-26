from __future__ import annotations

import unittest

from operational_branch import (
    WorkflowCandidate,
    WorkflowDisposition,
    WorkflowDomain,
    candidate_disposition,
    operational_plan,
)


class OperationalBranchTests(unittest.TestCase):
    def candidate(self, name: str, **changes) -> WorkflowCandidate:
        values = {
            "name": name,
            "domain": WorkflowDomain.CI_BUILD,
            "probability": 0.7,
            "impact": 0.8,
            "human_time_saved": 1.0,
            "preparation_leverage": 1.0,
            "cost": 0.2,
        }
        values.update(changes)
        return WorkflowCandidate(**values)

    def test_unchanged_failed_retry_is_quarantined(self):
        disposition, reason = candidate_disposition(
            self.candidate("same-command-again", unchanged_retry=True)
        )
        self.assertEqual(disposition, WorkflowDisposition.QUARANTINE)
        self.assertEqual(reason, "unchanged-failed-retry")

    def test_read_only_local_validation_is_prepared_ahead_of_retry_storm(self):
        plan = operational_plan(
            [
                self.candidate(
                    "cached-local-validation",
                    probability=0.65,
                    read_only=True,
                    cost=0.05,
                    human_time_saved=2.0,
                ),
                self.candidate(
                    "retry-identical-job",
                    probability=0.9,
                    unchanged_retry=True,
                    cost=0.01,
                ),
            ],
            verified_state="last-green-build",
        )
        self.assertEqual(plan["branches"][0]["name"], "cached-local-validation")
        retry = next(item for item in plan["branches"] if item["name"] == "retry-identical-job")
        self.assertEqual(retry["disposition"], "quarantine")
        self.assertFalse(plan["unchanged_retry_allowed"])

    def test_explicit_retry_after_waits_without_spinning(self):
        disposition, reason = candidate_disposition(
            self.candidate("quota-retry", retry_after_seconds=900)
        )
        self.assertEqual(disposition, WorkflowDisposition.WAIT)
        self.assertEqual(reason, "explicit-retry-after")

    def test_web_candidate_requires_rollback_before_mutating_deployment(self):
        disposition, reason = candidate_disposition(
            self.candidate(
                "promote-web-candidate",
                domain=WorkflowDomain.WEBSITE_DEPLOYMENT,
                rollback_prepared=False,
                external_side_effect=False,
            )
        )
        self.assertEqual(disposition, WorkflowDisposition.HOLD)
        self.assertEqual(reason, "rollback-not-prepared")

    def test_external_publish_stops_at_authority_boundary(self):
        plan = operational_plan(
            [
                self.candidate(
                    "prepare-social-draft",
                    domain=WorkflowDomain.EXTERNAL_CONTENT,
                    reversible=True,
                    probability=0.8,
                ),
                self.candidate(
                    "publish-social-draft",
                    domain=WorkflowDomain.EXTERNAL_CONTENT,
                    external_side_effect=True,
                    authorization_required=True,
                    probability=0.75,
                ),
            ],
            verified_state="draft-only",
        )
        publish = next(item for item in plan["branches"] if item["name"] == "publish-social-draft")
        self.assertEqual(publish["disposition"], "wait-boundary")
        self.assertFalse(plan["publish_allowed"])
        self.assertFalse(publish["grants_authority"])

    def test_alternate_route_does_not_broaden_trust(self):
        plan = operational_plan(
            [
                self.candidate(
                    "authorized-cache-route",
                    alternate_authorized_route=True,
                    read_only=True,
                ),
                self.candidate(
                    "guess-different-target",
                    trust_broadening=True,
                    probability=0.95,
                ),
            ],
            verified_state="target-A",
        )
        trusted = next(item for item in plan["branches"] if item["name"] == "authorized-cache-route")
        broaden = next(item for item in plan["branches"] if item["name"] == "guess-different-target")
        self.assertEqual(trusted["disposition"], "prepare")
        self.assertEqual(broaden["disposition"], "quarantine")
        self.assertFalse(plan["trust_broadening_allowed"])

    def test_verified_deployment_is_never_displaced_by_speculation(self):
        disposition, reason = candidate_disposition(
            self.candidate(
                "replace-current-site",
                domain=WorkflowDomain.WEBSITE_DEPLOYMENT,
                rollback_prepared=True,
                preserves_verified_state=False,
            )
        )
        self.assertEqual(disposition, WorkflowDisposition.HOLD)
        self.assertEqual(reason, "would-displace-verified-state")


if __name__ == "__main__":
    unittest.main()
