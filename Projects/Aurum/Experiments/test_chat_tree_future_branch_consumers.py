from __future__ import annotations

import unittest

from chat_tree_bridge import BridgeError, handle_request


class ChatTreeFutureBranchConsumerTests(unittest.TestCase):
    def test_human_projection_keeps_verified_truth_separate(self):
        response = handle_request(
            {
                "command": "project_human_futures",
                "verified_state": "READY_TO_BOOT",
                "lkg": "slot-a",
                "likely_next": [
                    {"state": "boot-mixed-result", "probability": 0.25},
                    {"state": "physical-hopper-boot-success", "probability": 0.70},
                ],
                "blockers": ["physical-hopper-boot-proof"],
            }
        )
        projection = response["projection"]
        self.assertEqual(projection["verified"]["state"], "READY_TO_BOOT")
        self.assertEqual(projection["verified"]["lkg"], "slot-a")
        self.assertEqual(projection["likely_next"][0]["state"], "physical-hopper-boot-success")
        self.assertFalse(projection["likely_next"][0]["verified"])
        self.assertFalse(projection["authority_from_projection"])
        self.assertFalse(response["authority_granted"])
        self.assertFalse(response["physical_proof_inferred"])
        self.assertFalse(response["side_effects_performed"])

    def test_operational_plan_prepares_safe_branch_and_holds_external_effect(self):
        response = handle_request(
            {
                "command": "plan_operational_futures",
                "verified_state": "ci-green",
                "candidates": [
                    {
                        "name": "inspect-ci-logs",
                        "domain": "ci-build",
                        "probability": 0.82,
                        "impact": 0.8,
                        "human_time_saved": 3.0,
                        "preparation_leverage": 1.0,
                        "cost": 0.2,
                        "read_only": True,
                    },
                    {
                        "name": "publish-website",
                        "domain": "website-deployment",
                        "probability": 0.70,
                        "impact": 0.9,
                        "human_time_saved": 2.0,
                        "preparation_leverage": 0.8,
                        "cost": 0.5,
                        "rollback_prepared": True,
                        "external_side_effect": True,
                        "authorization_required": True,
                    },
                    {
                        "name": "retry-identical-failure",
                        "domain": "ci-build",
                        "probability": 0.75,
                        "impact": 0.5,
                        "human_time_saved": 1.0,
                        "preparation_leverage": 0.5,
                        "cost": 0.2,
                        "read_only": True,
                        "unchanged_retry": True,
                    },
                ],
            }
        )
        plan = response["plan"]
        by_name = {item["name"]: item for item in plan["branches"]}
        self.assertEqual(by_name["inspect-ci-logs"]["disposition"], "prepare")
        self.assertEqual(by_name["publish-website"]["disposition"], "wait-boundary")
        self.assertEqual(by_name["retry-identical-failure"]["disposition"], "quarantine")
        self.assertFalse(plan["external_action_allowed"])
        self.assertFalse(plan["publish_allowed"])
        self.assertFalse(response["authority_granted"])
        self.assertFalse(response["side_effects_performed"])

    def test_direct_bridge_fails_closed_on_string_boolean(self):
        with self.assertRaises(BridgeError):
            handle_request(
                {
                    "command": "plan_operational_futures",
                    "verified_state": "ci-green",
                    "candidates": [
                        {
                            "name": "unsafe-coercion",
                            "domain": "ci-build",
                            "probability": 0.8,
                            "impact": 0.8,
                            "human_time_saved": 1.0,
                            "preparation_leverage": 1.0,
                            "cost": 0.2,
                            "read_only": "false",
                        }
                    ],
                }
            )

    def test_invalid_human_probability_fails_closed(self):
        with self.assertRaises(ValueError):
            handle_request(
                {
                    "command": "project_human_futures",
                    "verified_state": "known",
                    "likely_next": [{"state": "impossible", "probability": 1.2}],
                }
            )


if __name__ == "__main__":
    unittest.main()
