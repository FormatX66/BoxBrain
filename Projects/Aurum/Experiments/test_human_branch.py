from __future__ import annotations

import unittest

from human_branch import (
    IdentityHypothesis,
    IntentCandidate,
    PreferenceCandidate,
    identity_session_decision,
    preference_decision,
    rank_intents,
    status_projection,
)


class HumanBranchTests(unittest.TestCase):
    def test_stale_intent_expires_instead_of_staying_warm(self):
        ranked = rank_intents(
            [
                IntentCandidate("old-plan", 0.8, 0.1, 0.9, reversible_prestage=True),
                IntentCandidate("fresh-plan", 0.5, 0.9, 0.8, reversible_prestage=True),
            ]
        )
        old = next(item for item in ranked if item["name"] == "old-plan")
        fresh = next(item for item in ranked if item["name"] == "fresh-plan")
        self.assertEqual(old["disposition"], "expire")
        self.assertEqual(fresh["disposition"], "prestage")

    def test_high_impact_intent_never_crosses_boundary_from_probability(self):
        ranked = rank_intents(
            [IntentCandidate("wipe-disk", 0.98, 1.0, 1.0, reversible_prestage=True, high_impact_boundary=True)]
        )
        self.assertEqual(ranked[0]["disposition"], "wait-boundary")
        self.assertFalse(ranked[0]["grants_authority"])

    def test_single_gui_observation_cannot_switch_preference(self):
        result = preference_decision(
            PreferenceCandidate(
                "compact-layout",
                positive_observations=1,
                negative_observations=0,
                familiarity=0.4,
                rollback_available=True,
            ),
            current_preference="classic-layout",
        )
        self.assertEqual(result["disposition"], "keep-warm")
        self.assertFalse(result["single_observation_can_switch"])

    def test_repeated_gui_preference_can_adapt_only_with_rollback(self):
        safe = preference_decision(
            PreferenceCandidate(
                "compact-layout",
                positive_observations=5,
                negative_observations=1,
                familiarity=0.8,
                rollback_available=True,
            ),
            current_preference="classic-layout",
        )
        unsafe = preference_decision(
            PreferenceCandidate(
                "compact-layout",
                positive_observations=5,
                negative_observations=1,
                familiarity=0.8,
                rollback_available=False,
            ),
            current_preference="classic-layout",
        )
        self.assertEqual(safe["disposition"], "adapt-reversibly")
        self.assertTrue(safe["rollback_required"])
        self.assertEqual(unsafe["disposition"], "keep-warm")

    def test_identity_prediction_cannot_raise_privilege(self):
        result = identity_session_decision(
            [IdentityHypothesis("likely-user", confidence=0.99, signal_quality=0.99)],
            current_privilege=1,
            requested_privilege=2,
            authentication_threshold=0.8,
        )
        self.assertEqual(result["disposition"], "require-auth")
        self.assertEqual(result["effective_privilege"], 1)
        self.assertFalse(result["prediction_can_raise_privilege"])
        self.assertFalse(result["authentication_threshold_lowered"])

    def test_ambiguous_identity_reduces_or_holds_privilege(self):
        result = identity_session_decision(
            [
                IdentityHypothesis("person-a", confidence=0.86, signal_quality=0.9),
                IdentityHypothesis("person-b", confidence=0.82, signal_quality=0.9),
            ],
            current_privilege=2,
            requested_privilege=1,
            authentication_threshold=0.7,
        )
        self.assertTrue(result["ambiguous"])
        self.assertEqual(result["disposition"], "reduce-privilege")
        self.assertEqual(result["effective_privilege"], 1)

    def test_status_projection_keeps_speculation_separate(self):
        projection = status_projection(
            verified_state="READY_TO_BOOT",
            likely_next=[("boot-success", 0.6), ("boot-mixed", 0.3)],
            lkg="Gen0",
            blockers=["physical boot required"],
        )
        self.assertEqual(projection["verified"]["state"], "READY_TO_BOOT")
        self.assertFalse(projection["likely_next"][0]["verified"])
        self.assertFalse(projection["speculation_rendered_as_verified"])
        self.assertFalse(projection["authority_from_projection"])


if __name__ == "__main__":
    unittest.main()
