from __future__ import annotations
from dataclasses import replace
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];FIELD=ROOT/"field";sys.path.insert(0,str(ROOT));sys.path.insert(0,str(FIELD))
from external_prerequisite_evidence import (
    apply_adaptive_shell_iteration_observation_readiness_evidence,
    apply_adaptive_shell_live_trial_evidence,
    apply_adaptive_shell_live_trial_readiness_evidence,
    apply_external_prerequisite_evidence,
)
from local_capability_verification import verify_local_capability_for_gap
from native_gap_catalog import get_native_semantic_gap
from run_native_autonomous_chain import _is_external_prerequisite_block

class LocalCapabilityVerificationTests(unittest.TestCase):
    def _console_deployment_evidence(self):
        return {
            "schema":"aurum-bbpi4-console-evidence-v1","verified":True,
            "node_id":"bbpi4feed1234567","route":"10.12.194.1",
            "ssh_host_key_fingerprint":"SHA256:0SyJhmydZNm5NQsr1lBCf6nqTDiSQRlVzKBtlrvYTGQ",
            "console":{"command":"/usr/local/bin/aurum","command_sha256":"a"*64,"module":"/opt/boxbrain/codelation/seed/aurum_console.py","module_sha256":"b"*64,"dialogue_supervisor_sha256":"c"*64,"dialogue_only":True,"host_actuation":False,"api_key_persisted":False},
        }
    def _iteration_observation_evidence(self):
        return {
            "schema":"aurum-adaptive-shell-iteration-observation-readiness-evidence-v1",
            "kind":"adaptive-shell-iteration-observation-readiness",
            "source":"aurum-bbpi4-console-status-proof","verified":True,
            "node_id":"bbpi4feed1234567","route":"10.12.194.1",
            "ssh_host_key_fingerprint":"SHA256:0SyJhmydZNm5NQsr1lBCf6nqTDiSQRlVzKBtlrvYTGQ",
            "observed_at":1000,"expires_at":1300,
            "console":{"status_verified":True,"command":"/usr/local/bin/aurum","command_sha256":"a"*64,"module":"/opt/boxbrain/codelation/seed/aurum_console.py","module_sha256":"b"*64,"dialogue_supervisor_sha256":"c"*64,"identity":"BBPI4/Aurum","mind_version":2,"mind_sha256":"d"*64,"dialogue_only":True,"host_actuation":False,"api_key_persisted":False},
            "observation":{"type":"console-status-and-capability-snapshot","read_only":True,"dialogue_generated":False,"user_content_captured":False},
            "permission":{"present":True,"scope":"adaptive-shell-iteration-observation","authorization_reference":"operator-next-iteration"},
            "proof_view":{"present":True,"mind_sha256":"d"*64,"user_content_captured":False},
            "authority_granted":False,"persistent_change_authorized":False,
        }
    def _readiness_evidence(self):
        return {
            "schema":"aurum-adaptive-shell-live-trial-readiness-evidence-v1",
            "kind":"adaptive-shell-live-trial-readiness",
            "source":"aurum-windows-usb-kvm-bounded-proof",
            "verified":True,
            "node_id":"bbpi4feed1234567",
            "route":"10.12.194.1",
            "ssh_host_key_fingerprint":"SHA256:0SyJhmydZNm5NQsr1lBCf6nqTDiSQRlVzKBtlrvYTGQ",
            "observed_at":1000,
            "expires_at":1300,
            "display":{"verified":True,"http_status":200,"content_type":"multipart/x-mixed-replace; boundary=frame","sample_bytes":4096,"sample_sha256":"a"*64},
            "input":{"verified":True,"action":"release","acknowledged":True,"before_neutral":True,"after_neutral":True},
            "permission":{"present":True,"scope":"bounded-adaptive-shell-live-trial","authorization_reference":"operator-test"},
            "rollback":{"verified":True,"method":"neutral-hid-release-and-ephemeral-state"},
            "proof_view":{"present":True,"display_sample_sha256":"a"*64},
        }
    def _trial_evidence(self):
        return {
            "schema":"aurum-adaptive-shell-live-trial-evidence-v1",
            "kind":"adaptive-shell-bounded-live-trial",
            "source":"aurum-ephemeral-shell-state-trial",
            "verified":True,
            "node_id":"bbpi4feed1234567",
            "route":"10.12.194.1",
            "observed_at":1000,
            "expires_at":1300,
            "readiness_evidence_sha256":"b"*64,
            "trial_identity":"c"*64,
            "proposal":{"verified":True,"delta":"add=terminal;remove=none;evidence=coding-confidence-high"},
            "application":{"verified":True,"scope":"ephemeral-trial-workspace","persistent":False,"candidate_sha256":"d"*64},
            "rollback":{"verified":True,"baseline_sha256":"e"*64,"restored_sha256":"e"*64},
            "proof_view":{"present":True,"trial_identity":"c"*64},
            "safety":{"raw_disk_changed":False,"firmware_changed":False,"bootloader_changed":False,"service_state_changed":False,"persistent_interface_changed":False},
        }
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
    def test_fresh_neutral_carrier_and_permission_evidence_completes_readiness(self):
        gap=get_native_semantic_gap("adaptive_shell_live_trial_readiness");self.assertIsNotNone(gap)
        physical=apply_external_prerequisite_evidence(gap,{"schema":"aurum-external-prerequisite-evidence-v0","kind":"bbpi4-physical-presence","source":"aurum-public-controller-fresh-node","verified":True,"node_id":"bbpi4feed1234567","name":"BBPI4","carrier":"https-outbound","last_seen":990,"observed_at":1000,"expires_at":1300},now=1010)
        applied=apply_adaptive_shell_live_trial_readiness_evidence(physical.spec,self._readiness_evidence(),expected_node_id="bbpi4feed1234567",now=1010)
        self.assertTrue(applied.applied);self.assertFalse(applied.evidence["authority_granted"]);self.assertFalse(applied.evidence["persistent_change_authorized"])
        verified=verify_local_capability_for_gap(applied.spec,"required-condition-classifier")
        self.assertTrue(verified.verified);self.assertEqual(verified.invocation_output,"ready-for-bounded-live-trial")
    def test_readiness_rejects_non_neutral_input_or_wrong_node(self):
        gap=get_native_semantic_gap("adaptive_shell_live_trial_readiness");self.assertIsNotNone(gap)
        invocation=dict(gap.invocation_arguments);invocation["physical_node_present"]="yes"
        from dataclasses import replace
        physical=replace(gap,invocation_arguments=invocation)
        unsafe=self._readiness_evidence();unsafe["input"]["action"]="key"
        rejected=apply_adaptive_shell_live_trial_readiness_evidence(physical,unsafe,expected_node_id="bbpi4feed1234567",now=1010)
        self.assertFalse(rejected.applied);self.assertEqual(rejected.reason,"input-proof-not-neutral")
        wrong=apply_adaptive_shell_live_trial_readiness_evidence(physical,self._readiness_evidence(),expected_node_id="different",now=1010)
        self.assertFalse(wrong.applied);self.assertEqual(wrong.reason,"readiness-node-identity-mismatch")
    def test_bounded_live_trial_evidence_is_classified_without_persistent_authority(self):
        gap=get_native_semantic_gap("adaptive_shell_live_trial");self.assertIsNotNone(gap)
        applied=apply_adaptive_shell_live_trial_evidence(gap,self._trial_evidence(),now=1010)
        self.assertTrue(applied.applied);self.assertFalse(applied.evidence["authority_granted"]);self.assertFalse(applied.evidence["persistent_change"])
        verified=verify_local_capability_for_gap(applied.spec,"required-condition-classifier")
        self.assertTrue(verified.verified);self.assertEqual(verified.invocation_output,"bounded-live-trial-passed")
        unsafe=self._trial_evidence();unsafe["safety"]["persistent_interface_changed"]=True
        rejected=apply_adaptive_shell_live_trial_evidence(gap,unsafe,now=1010)
        self.assertFalse(rejected.applied);self.assertEqual(rejected.reason,"trial-safety-boundary-invalid")
    def test_next_iteration_planning_requires_fresh_observation_and_permission(self):
        gap=get_native_semantic_gap("adaptive_shell_next_iteration_planning");self.assertIsNotNone(gap)
        verified=verify_local_capability_for_gap(gap,"required-condition-classifier")
        self.assertTrue(verified.verified);self.assertEqual(verified.invocation_output,"next-iteration-observation-gated")
        self.assertFalse(verified.authority_granted);self.assertFalse(verified.routed_to_host)
        invocation=dict(gap.invocation_arguments);invocation["new_permission_required"]="no"
        blocked=verify_local_capability_for_gap(replace(gap,invocation_arguments=invocation),"required-condition-classifier")
        self.assertTrue(blocked.verified);self.assertEqual(blocked.invocation_output,"blocked-new-permission-required")
    def test_iteration_observation_readiness_uses_fresh_dialogue_free_console_proof(self):
        gap=get_native_semantic_gap("adaptive_shell_iteration_observation_readiness");self.assertIsNotNone(gap)
        initial=verify_local_capability_for_gap(gap,"required-condition-classifier")
        self.assertTrue(initial.verified);self.assertEqual(initial.invocation_output,"blocked-console-observation-fresh")
        applied=apply_adaptive_shell_iteration_observation_readiness_evidence(gap,self._iteration_observation_evidence(),self._console_deployment_evidence(),now=1010)
        self.assertTrue(applied.applied);self.assertFalse(applied.evidence["authority_granted"]);self.assertFalse(applied.evidence["user_content_captured"])
        verified=verify_local_capability_for_gap(applied.spec,"required-condition-classifier")
        self.assertTrue(verified.verified);self.assertEqual(verified.invocation_output,"ready-for-bounded-iteration-observation")
        unsafe=self._iteration_observation_evidence();unsafe["observation"]["user_content_captured"]=True
        rejected=apply_adaptive_shell_iteration_observation_readiness_evidence(gap,unsafe,self._console_deployment_evidence(),now=1010)
        self.assertFalse(rejected.applied);self.assertEqual(rejected.reason,"iteration-observation-content-boundary-invalid")

if __name__=="__main__":unittest.main(verbosity=2)
