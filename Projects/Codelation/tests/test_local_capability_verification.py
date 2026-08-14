from __future__ import annotations
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];FIELD=ROOT/"field";sys.path.insert(0,str(ROOT));sys.path.insert(0,str(FIELD))
from external_prerequisite_evidence import apply_external_prerequisite_evidence
from local_capability_verification import verify_local_capability_for_gap
from native_gap_catalog import get_native_semantic_gap
from run_native_autonomous_chain import _is_external_prerequisite_block

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
    def test_live_trial_readiness_block_is_safe_external_stop(self):
        gap=get_native_semantic_gap("adaptive_shell_live_trial_readiness");self.assertIsNotNone(gap)
        v=self._v("adaptive_shell_live_trial_readiness","required-condition-classifier")
        self.assertEqual(v.invocation_output,"blocked-physical-node")
        self.assertTrue(_is_external_prerequisite_block(gap,v.invocation_output))
    def test_fresh_physical_evidence_changes_only_physical_presence(self):
        gap=get_native_semantic_gap("adaptive_shell_live_trial_readiness");self.assertIsNotNone(gap)
        evidence={
            "schema":"aurum-external-prerequisite-evidence-v0",
            "kind":"bbpi4-physical-presence",
            "source":"aurum-public-controller-fresh-node",
            "verified":True,
            "node_id":"bbpi4feed1234567",
            "name":"BBPI4",
            "carrier":"https-outbound",
            "last_seen":990,
            "observed_at":1000,
            "expires_at":1300,
        }
        applied=apply_external_prerequisite_evidence(gap,evidence,now=1010)
        self.assertTrue(applied.applied);self.assertEqual(applied.reason,"fresh-physical-node-evidence")
        self.assertEqual(applied.spec.invocation_arguments["physical_node_present"],"yes")
        self.assertEqual(applied.spec.invocation_arguments["display_carrier_verified"],"no")
        self.assertEqual(applied.spec.invocation_arguments["input_carrier_verified"],"no")
        self.assertEqual(applied.spec.invocation_arguments["permission_present"],"no")
        self.assertFalse(applied.evidence["authority_granted"]);self.assertFalse(applied.evidence["permission_granted"])
        v=verify_local_capability_for_gap(applied.spec,"required-condition-classifier")
        self.assertTrue(v.verified);self.assertEqual(v.invocation_output,"blocked-display-carrier-verified")
        self.assertTrue(_is_external_prerequisite_block(applied.spec,v.invocation_output))
    def test_stale_or_controller_presence_evidence_is_rejected(self):
        gap=get_native_semantic_gap("adaptive_shell_live_trial_readiness");self.assertIsNotNone(gap)
        base={
            "schema":"aurum-external-prerequisite-evidence-v0",
            "kind":"bbpi4-physical-presence",
            "source":"aurum-public-controller-fresh-node",
            "verified":True,
            "node_id":"bbpi4feed1234567",
            "name":"BBPI4",
            "carrier":"https-outbound",
            "last_seen":990,
            "observed_at":1000,
            "expires_at":1300,
        }
        stale=apply_external_prerequisite_evidence(gap,base,now=1400)
        self.assertFalse(stale.applied);self.assertEqual(stale.reason,"evidence-expired")
        controller=dict(base);controller["node_id"]="85404f41d5507372"
        rejected=apply_external_prerequisite_evidence(gap,controller,now=1010)
        self.assertFalse(rejected.applied);self.assertEqual(rejected.reason,"physical-node-identity-invalid")

if __name__=="__main__":unittest.main(verbosity=2)
