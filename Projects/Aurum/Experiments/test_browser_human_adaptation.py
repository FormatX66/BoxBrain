from __future__ import annotations

import unittest
from pathlib import Path

from browser_human_adaptation import BrowserPreferenceEvidence, browser_preference_decision


ROOT = Path(__file__).resolve().parents[3]
JS = ROOT / "Web" / "Aurum-Arkmatx" / "human-adaptation-v1.js"
LAB = ROOT / "Web" / "Aurum-Arkmatx" / "human-adaptation-lab.html"


class BrowserHumanAdaptationTests(unittest.TestCase):
    def evidence(self, **changes) -> BrowserPreferenceEvidence:
        values = {
            "name": "future-branch-detail-expanded",
            "positive_sessions": 3,
            "negative_sessions": 0,
            "age_days": 1.0,
            "rollback_available": True,
        }
        values.update(changes)
        return BrowserPreferenceEvidence(**values)

    def test_single_session_cannot_change_default(self):
        result = browser_preference_decision(
            self.evidence(positive_sessions=1),
            current_preference="collapsed",
        )
        self.assertEqual(result["disposition"], "keep-warm")
        self.assertFalse(result["single_observation_can_switch"])

    def test_repeated_distinct_sessions_can_adapt_reversibly(self):
        result = browser_preference_decision(
            self.evidence(),
            current_preference="collapsed",
        )
        self.assertEqual(result["disposition"], "adapt-reversibly")
        self.assertTrue(result["rollback_required"])
        self.assertTrue(result["reset_available"])

    def test_conflicting_evidence_keeps_preference_warm(self):
        result = browser_preference_decision(
            self.evidence(positive_sessions=3, negative_sessions=2),
            current_preference="collapsed",
        )
        self.assertEqual(result["disposition"], "keep-warm")

    def test_missing_rollback_blocks_adaptation(self):
        result = browser_preference_decision(
            self.evidence(rollback_available=False),
            current_preference="collapsed",
        )
        self.assertEqual(result["disposition"], "keep-warm")

    def test_stale_evidence_expires(self):
        result = browser_preference_decision(
            self.evidence(age_days=31),
            current_preference="collapsed",
        )
        self.assertTrue(result["expired"])
        self.assertEqual(result["disposition"], "keep-current")

    def test_browser_adaptation_never_creates_authority_or_identity(self):
        result = browser_preference_decision(
            self.evidence(),
            current_preference="collapsed",
        )
        for key in (
            "grants_authority",
            "server_state_mutation_allowed",
            "external_action_allowed",
            "destructive_action_allowed",
            "identity_inference_allowed",
            "authentication_threshold_change_allowed",
            "privilege_change_allowed",
        ):
            self.assertFalse(result[key], key)
        self.assertEqual(result["storage_scope"], "local-browser-only")
        self.assertTrue(result["presentation_only"])

    def test_browser_lab_loads_local_only_consumer_with_reset(self):
        js = JS.read_text(encoding="utf-8")
        lab = LAB.read_text(encoding="utf-8")
        self.assertIn("human-adaptation-v1.js", lab)
        self.assertIn("data-id=\"future-branch\"", lab)
        self.assertIn("localStorage", js)
        self.assertIn("sessionStorage", js)
        self.assertIn("MIN_EVIDENCE=3", js)
        self.assertIn("Reset learned view", js)
        self.assertIn("grantsAuthority:false", js)
        self.assertIn("serverMutationAllowed:false", js)
        self.assertIn("identityInferenceAllowed:false", js)
        self.assertNotIn("fetch(", js)
        self.assertNotIn("XMLHttpRequest", js)


if __name__ == "__main__":
    unittest.main()
