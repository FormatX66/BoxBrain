from __future__ import annotations
import sys,unittest
from pathlib import Path
FIELD=Path(__file__).resolve().parents[1]/"field";sys.path.insert(0,str(FIELD))
from local_capability_verification import verify_local_capability_for_gap
from native_gap_catalog import get_native_semantic_gap

class LocalCapabilityVerificationTests(unittest.TestCase):
    def _v(self,gap_name,capability):
        gap=get_native_semantic_gap(gap_name);self.assertIsNotNone(gap);v=verify_local_capability_for_gap(gap,capability);self.assertTrue(v.verified);self.assertEqual(v.passed,v.examples);self.assertFalse(v.authority_granted);self.assertFalse(v.routed_to_host);return v
    def test_io_plan(self):self.assertEqual(self._v("io_safe_port_choice","io-plan").invocation_output,"display-output")
    def test_labeled_projection(self):self.assertEqual(self._v("interface_human_state_projection","labeled-text-projection").invocation_output,"selected=text-dialogue;blocked=display-output;missing=visual-output")
    def test_required_conditions(self):self.assertEqual(self._v("io_binding_readiness","required-condition-classifier").invocation_output,"ready")
    def test_mode_selection(self):self.assertEqual(self._v("interface_mode_selection","thresholded-unique-best-selector").invocation_output,"coding")
    def test_stability_filter(self):self.assertEqual(self._v("interface_stability_budget","protected-token-filter").invocation_output,"wallpaper workspace")
    def test_reversible_delta(self):self.assertEqual(self._v("interface_adaptation_proposal","reversible-state-delta-projection").invocation_output,"add=terminal;remove=none;evidence=coding-confidence-high")
    def test_preference_evidence(self):self.assertEqual(self._v("interface_user_feedback_learning","bounded-preference-evidence").invocation_output,"prefer=terminal workspace;avoid=none;lock=terminal;neutral=tips")
    def test_categorical_resource_policy(self):self.assertEqual(self._v("resource_context_proposal","categorical-token-policy").invocation_output,"cpu memory storage")

if __name__=="__main__":unittest.main(verbosity=2)
