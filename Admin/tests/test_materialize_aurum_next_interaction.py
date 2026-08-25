"""Tests for zero-authority Future Branch next-interaction materialization."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import Admin.materialize_aurum_next_interaction as materializer


SEED_CONTRACT = "\n".join(
    (
        "INTERACTION — treat likely next user questions and status checks as first-class Future Branches.",
        "maintain a parallel interaction frontier.",
        "HANDOFF — continuously materialize a ready-to-render next-interaction packet",
        "activated by the user's next real interaction, not by a clock.",
        "Never create a scheduled morning report, reminder, or notification to simulate prediction.",
    )
)


class MaterializeAurumNextInteractionTests(unittest.TestCase):
    def write_json(self, path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def branch(self) -> dict:
        return {
            "schema": "aurum-future-branch-state-test",
            "current_program": "Canonical state is safe and waiting at a human boundary.",
            "canonical_evidence": {
                "release": {
                    "source_commit": "a" * 40,
                    "state": "READY_TO_FLASH",
                }
            },
            "live_controls": {
                "write_authority": True,
                "destructive_action_allowed": True,
                "next_gate": "explicit-guarded-flash-authorization",
            },
            "likely_user_inputs": [
                {
                    "rank": 2,
                    "input_family": "status-or-so",
                    "prepared_response": "Report current canonical state.",
                    "action_if_safe": "Refresh evidence before reporting.",
                },
                {
                    "rank": 1,
                    "input_family": "explicit-guarded-flash-authorization",
                    "prepared_response": "Bind authority only after a live recheck.",
                    "action_if_safe": "Re-read canonical evidence before any write.",
                },
            ],
        }

    def paths(self, root: Path) -> tuple[Path, Path, Path]:
        return (
            root / "Projects/Aurum/future-branches.json",
            root / "Projects/Aurum/next-interaction-packet.json",
            root / "Prompts/FutureBranchSeed.txt",
        )

    def test_materialized_packet_is_zero_authority_and_requires_live_recheck(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            branch_path, packet_path, seed_path = self.paths(root)
            self.write_json(branch_path, self.branch())
            seed_path.parent.mkdir(parents=True, exist_ok=True)
            seed_path.write_text(SEED_CONTRACT, encoding="utf-8")

            with (
                patch.object(materializer, "BRANCH", branch_path),
                patch.object(materializer, "PACKET", packet_path),
                patch.object(materializer, "SEED", seed_path),
            ):
                result = materializer.materialize()

            packet = result["packet"]
            saved_branch = json.loads(branch_path.read_text(encoding="utf-8"))

            self.assertTrue(result["changed"])
            self.assertFalse(packet["authority_granted"])
            self.assertFalse(packet["authority_snapshot_authoritative"])
            self.assertTrue(packet["time_sensitive_authority_requires_live_recheck"])
            self.assertFalse(packet["scheduled_simulation_allowed"])
            self.assertFalse(packet["physical_proof_inferred"])
            self.assertFalse(packet["lkg_mutation_allowed"])
            self.assertFalse(packet["human_action_inferred"])
            self.assertEqual(
                packet["consumption_gate"],
                "re-read-canonical-evidence-and-action-ownership-before-human-or-destructive-step",
            )
            self.assertEqual(packet["release_source_commit"], "a" * 40)
            self.assertEqual(packet["frontier"][0]["rank"], 1)
            self.assertTrue(
                all(
                    item["authority"] == "prediction-only-requires-live-consumption-recheck"
                    for item in packet["frontier"]
                )
            )
            # A materialized live-control value is deliberately only a snapshot;
            # even a stale True value cannot become packet authority.
            self.assertTrue(packet["live_controls_snapshot"]["write_authority"])
            self.assertFalse(packet["authority_snapshot_authoritative"])
            self.assertFalse(packet["authority_granted"])
            self.assertEqual(
                saved_branch["interaction_handoff"]["consumption_gate"],
                packet["consumption_gate"],
            )
            self.assertFalse(saved_branch["interaction_handoff"]["authority_snapshot_authoritative"])
            self.assertIn("must be revalidated live at consumption", saved_branch["current_program"])

    def test_ready_to_boot_receipt_promotes_physical_boot_frontier_without_granting_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            branch_path, packet_path, seed_path = self.paths(root)
            branch = self.branch()
            branch["current_program"] = (
                "Stale preflight says next_gate=explicit-guarded-flash-authorization and asks for another flash."
            )
            branch["live_controls"].update(
                {
                    "flash_receipt_matches_current_release": True,
                    "current_release_flash_ready_to_boot": True,
                }
            )
            branch["likely_user_inputs"].extend(
                [
                    {
                        "rank": 7,
                        "input_family": "physical-result-success",
                        "prepared_response": "Verify formal boot proof.",
                        "action_if_safe": "Continue protected regrow after boot proof.",
                    },
                    {
                        "rank": 5,
                        "input_family": "physical-result-mixed",
                        "prepared_response": "Preserve boot progress and repair only the deferred gate.",
                        "action_if_safe": "Collect evidence and repair the failed stage.",
                    },
                    {
                        "rank": 6,
                        "input_family": "physical-result-failure",
                        "prepared_response": "Classify the boot failure without touching LKG.",
                        "action_if_safe": "Use prepared diagnostics and fallback evidence.",
                    },
                    {
                        "rank": 3,
                        "input_family": "generic-prompt-intent-expansion",
                        "prepared_response": "Continue from next_gate=explicit-guarded-flash-authorization.",
                        "action_if_safe": "Advance safe work.",
                    },
                ]
            )
            self.write_json(branch_path, branch)
            seed_path.parent.mkdir(parents=True, exist_ok=True)
            seed_path.write_text(SEED_CONTRACT, encoding="utf-8")

            with (
                patch.object(materializer, "BRANCH", branch_path),
                patch.object(materializer, "PACKET", packet_path),
                patch.object(materializer, "SEED", seed_path),
            ):
                result = materializer.materialize()

            packet = result["packet"]
            saved_branch = json.loads(branch_path.read_text(encoding="utf-8"))
            families = [item["input_family"] for item in packet["frontier"]]
            self.assertEqual(
                families,
                [
                    "physical-result-success",
                    "physical-result-mixed",
                    "physical-result-failure",
                    "status-or-so",
                    "generic-prompt-intent-expansion",
                ],
            )
            self.assertEqual(packet["live_controls_snapshot"]["next_gate"], "physical-hopper-boot-proof")
            self.assertEqual(
                packet["live_controls_snapshot"]["physical_preflight_next_gate"],
                "explicit-guarded-flash-authorization",
            )
            self.assertEqual(packet["live_controls_snapshot"]["frontier_mode"], "post-flash-physical-boot")
            self.assertIn("effective next gate=physical-hopper-boot-proof", packet["current_program"])
            self.assertIn("Physical Hopper boot proof", packet["current_program"])
            self.assertNotIn("next_gate=explicit-guarded-flash-authorization", packet["current_program"])
            self.assertNotIn("explicit-guarded-flash-authorization", families)
            status = next(item for item in packet["frontier"] if item["input_family"] == "status-or-so")
            generic = next(
                item for item in packet["frontier"] if item["input_family"] == "generic-prompt-intent-expansion"
            )
            self.assertIn("physical-hopper-boot-proof", status["prepared_response"])
            self.assertNotIn("explicit-guarded-flash-authorization", status["prepared_response"])
            self.assertIn("physical-hopper-boot-proof", generic["prepared_response"])
            saved_families = [item["input_family"] for item in saved_branch["likely_user_inputs"][:5]]
            self.assertEqual(saved_families, families)
            self.assertNotEqual(saved_branch["likely_user_inputs"][0]["input_family"], "explicit-guarded-flash-authorization")
            self.assertNotIn("next_gate=explicit-guarded-flash-authorization", saved_branch["current_program"])
            self.assertFalse(packet["authority_granted"])
            self.assertFalse(packet["physical_proof_inferred"])

    def test_materialization_is_idempotent_after_packet_and_handoff_are_current(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            branch_path, packet_path, seed_path = self.paths(root)
            self.write_json(branch_path, self.branch())
            seed_path.parent.mkdir(parents=True, exist_ok=True)
            seed_path.write_text(SEED_CONTRACT, encoding="utf-8")

            with (
                patch.object(materializer, "BRANCH", branch_path),
                patch.object(materializer, "PACKET", packet_path),
                patch.object(materializer, "SEED", seed_path),
            ):
                first = materializer.materialize()
                second = materializer.materialize()

            self.assertTrue(first["changed"])
            self.assertFalse(second["changed"])

    def test_incomplete_seed_contract_fails_closed_without_creating_packet(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            branch_path, packet_path, seed_path = self.paths(root)
            self.write_json(branch_path, self.branch())
            seed_path.parent.mkdir(parents=True, exist_ok=True)
            seed_path.write_text("partial Future Branch prompt", encoding="utf-8")

            with (
                patch.object(materializer, "BRANCH", branch_path),
                patch.object(materializer, "PACKET", packet_path),
                patch.object(materializer, "SEED", seed_path),
            ):
                with self.assertRaises(ValueError):
                    materializer.materialize()

            self.assertFalse(packet_path.exists())


if __name__ == "__main__":
    unittest.main()
