from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from Admin.reconstruct_aurum_state import ReconstructionError, reconstruct


class AurumRestartReconstructionTests(unittest.TestCase):
    def write_json(self, root: Path, relative: str, value: dict) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def fixture_root(self, *, preflight_write_authority: bool = False) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)

        source = "a" * 40
        self.write_json(
            root,
            "Projects/Aurum/completion-plan.json",
            {
                "goal": "prove restart continuity",
                "latest_release_source_commit": source,
                "release_state": "READY_TO_FLASH",
                "gates": [
                    {
                        "id": "foundation",
                        "lane": "foundation",
                        "depends_on": [],
                        "state": "passed-current-head",
                        "ready_now": True,
                        "proof": "foundation passed",
                    },
                    {
                        "id": "physical-flash",
                        "lane": "physical",
                        "depends_on": ["foundation"],
                        "state": "ready-for-guarded-preflight-explicit-authority-pending",
                        "ready_now": False,
                        "proof": "raw readback",
                    },
                ],
            },
        )
        self.write_json(
            root,
            "Projects/Aurum/Release/latest-tinyseed-handoff.json",
            {
                "state": "READY_TO_FLASH",
                "source_commit": source,
                "gates": {"x86_build": "passed", "physical_boot": "pending"},
                "artifacts": {"x86": {"name": "Aurum-TinySeed-amd64.iso"}},
            },
        )
        self.write_json(
            root,
            "Projects/Aurum/Recovery/latest-tinyseed-physical-preflight.json",
            {
                "release_source_commit": source,
                "release_state": "READY_TO_FLASH",
                "preflight_state": "READY_FOR_GUARDED_FLASH_PREFLIGHT",
                "next_gate": "explicit-guarded-flash-authorization",
                "write_authority": preflight_write_authority,
                "destructive_action_allowed": preflight_write_authority,
                "physical_boot_proven": False,
                "guardian_forced_rollback_proven": False,
                "x86_sha256": "b" * 64,
                "authorization": {"authorization_state": "FRESH" if preflight_write_authority else "EXPIRED"},
                "usb_candidate": {
                    "model": "test usb",
                    "size_bytes": 64000000000,
                    "serial_sha256": "c" * 64,
                    "protected": False,
                    "is_boot": False,
                    "is_system": False,
                },
                "preexecution_recovery": {
                    "terminal_receipt_present": True,
                    "remote_repair": "unavailable",
                    "terminal_reason": "boxbrain-unreachable",
                    "manual_handoff_released": True,
                },
            },
        )
        self.write_json(
            root,
            "Projects/Aurum/future-branches.json",
            {
                "schema": "aurum-future-branch-state-test",
                "canonical_evidence": {
                    "fallback_carrier": {
                        "warm_current": True,
                        "canonical_payload_match": True,
                    }
                },
                "likely_user_inputs": [
                    {
                        "rank": 1,
                        "input_family": "explicit-guarded-flash-authorization",
                    }
                ],
                "likely_machine_outcomes": [
                    {
                        "rank": 1,
                        "state": "fresh-authority-triggers-live-reproof",
                    }
                ],
            },
        )
        return root

    def test_reconstructs_all_state_authority_continuity_answers(self):
        result = reconstruct(self.fixture_root())
        answers = result["answers"]
        self.assertEqual(result["schema"], "aurum-restart-reconstruction-v1")
        self.assertEqual(result["release"]["state"], "READY_TO_FLASH")
        self.assertEqual(
            answers["what_should_execute_next"]["canonical_next_gate"],
            "explicit-guarded-flash-authorization",
        )
        for key in (
            "what_am_i_building",
            "what_is_already_complete",
            "what_is_running_or_runnable",
            "what_is_blocked",
            "what_evidence_supports_this_state",
            "what_should_execute_next",
            "what_recovery_or_fallback_exists",
        ):
            self.assertIn(key, answers)
        self.assertFalse(result["authority"]["authority_granted"])
        self.assertFalse(result["physical_proof_inferred"])
        self.assertFalse(result["lkg_mutation_allowed"])

    def test_repository_authority_snapshot_can_never_grant_live_write_authority(self):
        result = reconstruct(self.fixture_root(preflight_write_authority=True))
        self.assertTrue(result["authority"]["snapshot_write_authority"])
        self.assertTrue(result["authority"]["snapshot_destructive_action_allowed"])
        self.assertFalse(result["authority"]["authority_snapshot_authoritative"])
        self.assertTrue(result["authority"]["live_recheck_required"])
        self.assertFalse(result["authority"]["authority_granted"])

    def test_release_provenance_mismatch_fails_closed(self):
        root = self.fixture_root()
        path = root / "Projects/Aurum/Recovery/latest-tinyseed-physical-preflight.json"
        preflight = json.loads(path.read_text(encoding="utf-8"))
        preflight["release_source_commit"] = "d" * 40
        path.write_text(json.dumps(preflight), encoding="utf-8")
        with self.assertRaisesRegex(ReconstructionError, "canonical release provenance mismatch"):
            reconstruct(root)

    def test_unknown_dependency_fails_closed(self):
        root = self.fixture_root()
        path = root / "Projects/Aurum/completion-plan.json"
        plan = json.loads(path.read_text(encoding="utf-8"))
        plan["gates"][1]["depends_on"] = ["missing-gate"]
        path.write_text(json.dumps(plan), encoding="utf-8")
        with self.assertRaisesRegex(ReconstructionError, "unknown dependencies"):
            reconstruct(root)

    def test_current_repository_state_reconstructs_consistently(self):
        root = Path(__file__).resolve().parents[2]
        result = reconstruct(root)
        self.assertEqual(
            result["release"]["source_commit"],
            result["answers"]["what_evidence_supports_this_state"]["source_files"]
            and result["release"]["source_commit"],
        )
        self.assertFalse(result["authority"]["authority_granted"])
        self.assertFalse(result["physical_proof_inferred"])
        self.assertIn("canonical_next_gate", result["answers"]["what_should_execute_next"])


if __name__ == "__main__":
    unittest.main()
