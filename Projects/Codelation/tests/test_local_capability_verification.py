from __future__ import annotations

import sys
import unittest
from pathlib import Path

FIELD = Path(__file__).resolve().parents[1] / "field"
sys.path.insert(0, str(FIELD))

from local_capability_verification import verify_local_capability_for_gap
from native_gap_catalog import get_native_semantic_gap


class LocalCapabilityVerificationTests(unittest.TestCase):
    def _verify(self, gap_name: str, capability: str):
        gap=get_native_semantic_gap(gap_name); self.assertIsNotNone(gap)
        verification=verify_local_capability_for_gap(gap,capability)
        self.assertTrue(verification.verified); self.assertEqual(verification.passed,verification.examples)
        self.assertFalse(verification.authority_granted); self.assertFalse(verification.routed_to_host)
        return verification

    def test_io_plan(self): self.assertEqual(self._verify("io_safe_port_choice","io-plan").invocation_output,"display-output")
    def test_labeled_projection(self): self.assertEqual(self._verify("interface_human_state_projection","labeled-text-projection").invocation_output,"selected=text-dialogue;blocked=display-output;missing=visual-output")
    def test_required_condition_classifier(self): self.assertEqual(self._verify("io_binding_readiness","required-condition-classifier").invocation_output,"ready")
    def test_thresholded_unique_best_selector(self): self.assertEqual(self._verify("interface_mode_selection","thresholded-unique-best-selector").invocation_output,"coding")
    def test_protected_token_filter(self): self.assertEqual(self._verify("interface_stability_budget","protected-token-filter").invocation_output,"wallpaper workspace")
    def test_reversible_delta_projection(self): self.assertEqual(self._verify("interface_adaptation_proposal","reversible-state-delta-projection").invocation_output,"add=terminal;remove=none;evidence=coding-confidence-high")
    def test_bounded_preference_evidence(self): self.assertEqual(self._verify("interface_user_feedback_learning","bounded-preference-evidence").invocation_output,"prefer=terminal workspace;avoid=none;lock=terminal;neutral=tips")


if __name__=="__main__": unittest.main(verbosity=2)
