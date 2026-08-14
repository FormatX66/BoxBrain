from __future__ import annotations

import sys
import unittest
from pathlib import Path

FIELD = Path(__file__).resolve().parents[1] / "field"
sys.path.insert(0, str(FIELD))

from local_capability_verification import verify_local_capability_for_gap
from native_gap_catalog import get_native_semantic_gap


class LocalCapabilityVerificationTests(unittest.TestCase):
    def test_io_plan_satisfies_safe_port_semantic_contract_without_authority(self):
        gap = get_native_semantic_gap("io_safe_port_choice")
        self.assertIsNotNone(gap)
        verification = verify_local_capability_for_gap(gap, "io-plan")
        self.assertTrue(verification.verified)
        self.assertEqual(verification.passed, verification.examples)
        self.assertEqual(verification.invocation_output, "display-output")
        self.assertFalse(verification.authority_granted)
        self.assertFalse(verification.routed_to_host)
        self.assertTrue(verification.implementation_sha256)
        self.assertTrue(verification.verification_identity)

    def test_labeled_projection_satisfies_human_state_projection_without_authority(self):
        gap = get_native_semantic_gap("interface_human_state_projection")
        self.assertIsNotNone(gap)
        verification = verify_local_capability_for_gap(gap, "labeled-text-projection")
        self.assertTrue(verification.verified)
        self.assertEqual(verification.passed, verification.examples)
        self.assertEqual(verification.invocation_output, "selected=text-dialogue;blocked=display-output;missing=visual-output")
        self.assertFalse(verification.authority_granted)
        self.assertFalse(verification.routed_to_host)

    def test_required_condition_classifier_satisfies_binding_readiness_without_authority(self):
        gap = get_native_semantic_gap("io_binding_readiness")
        self.assertIsNotNone(gap)
        verification = verify_local_capability_for_gap(gap, "required-condition-classifier")
        self.assertTrue(verification.verified)
        self.assertEqual(verification.passed, verification.examples)
        self.assertEqual(verification.invocation_output, "ready")
        self.assertFalse(verification.authority_granted)
        self.assertFalse(verification.routed_to_host)

    def test_thresholded_unique_best_selector_satisfies_mode_selection_without_authority(self):
        gap = get_native_semantic_gap("interface_mode_selection")
        self.assertIsNotNone(gap)
        verification = verify_local_capability_for_gap(gap, "thresholded-unique-best-selector")
        self.assertTrue(verification.verified)
        self.assertEqual(verification.passed, verification.examples)
        self.assertEqual(verification.invocation_output, "coding")
        self.assertFalse(verification.authority_granted)
        self.assertFalse(verification.routed_to_host)

    def test_protected_token_filter_satisfies_stability_budget_without_authority(self):
        gap = get_native_semantic_gap("interface_stability_budget")
        self.assertIsNotNone(gap)
        verification = verify_local_capability_for_gap(gap, "protected-token-filter")
        self.assertTrue(verification.verified)
        self.assertEqual(verification.passed, verification.examples)
        self.assertEqual(verification.invocation_output, "wallpaper workspace")
        self.assertFalse(verification.authority_granted)
        self.assertFalse(verification.routed_to_host)


if __name__ == "__main__":
    unittest.main(verbosity=2)
