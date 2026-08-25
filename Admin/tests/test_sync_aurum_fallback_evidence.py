from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from Admin.sync_aurum_fallback_evidence import sync_fallback_evidence


class FallbackEvidenceSyncTests(unittest.TestCase):
    def write(self, root: Path, relative: str, value: dict) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")

    def setup_state(
        self,
        root: Path,
        *,
        release_source: str = "a" * 40,
        provenance_source: str = "a" * 40,
        provenance_head: str = "b" * 40,
        matrix_head: str = "b" * 40,
        matrix_success: bool = True,
    ) -> None:
        self.write(
            root,
            "Projects/Aurum/Release/latest-tinyseed-handoff.json",
            {
                "schema": "aurum-tinyseed-handoff-v1",
                "state": "READY_TO_FLASH",
                "source_commit": release_source,
            },
        )
        self.write(
            root,
            "Projects/Aurum/Release/critical-workflows/aurum-tiny-seed-fallback-canonical-provenance.json",
            {
                "schema": "aurum-critical-workflow-evidence-v1",
                "status": "completed",
                "conclusion": "success",
                "head_sha": provenance_head,
                "canonical_release_source_commit": provenance_source,
                "canonical_payload_match": True,
            },
        )
        self.write(
            root,
            "Projects/Aurum/Release/critical-workflows/aurum-tiny-seed-x86-fallback-carrier-matrix-experiment.json",
            {
                "schema": "aurum-critical-workflow-evidence-v1",
                "status": "completed",
                "conclusion": "success" if matrix_success else "failure",
                "head_sha": matrix_head,
            },
        )
        self.write(
            root,
            "Projects/Aurum/future-branches.json",
            {
                "canonical_evidence": {},
                "live_controls": {},
                "likely_user_inputs": [
                    {
                        "input_family": "seed-method-pivot",
                        "prepared_response": "stale",
                        "action_if_safe": "stale",
                    }
                ],
            },
        )

    def test_same_head_current_release_is_warm_without_granting_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.setup_state(root)
            result = sync_fallback_evidence(root)
            branch = json.loads((root / "Projects/Aurum/future-branches.json").read_text())
            fallback = branch["canonical_evidence"]["fallback_carrier"]
            self.assertTrue(result["fallback_warm_current"])
            self.assertTrue(fallback["provenance_matches_current_release"])
            self.assertTrue(fallback["same_experimental_head"])
            self.assertFalse(fallback["physical_proof_inferred"])
            self.assertFalse(fallback["authority_granted"])
            self.assertTrue(branch["live_controls"]["fallback_carrier_current"])
            self.assertIn("current-release canonical-provenance proof", branch["likely_user_inputs"][0]["prepared_response"])

    def test_release_rollover_cools_old_fallback_even_when_old_runs_succeeded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.setup_state(root, release_source="c" * 40, provenance_source="a" * 40)
            result = sync_fallback_evidence(root)
            branch = json.loads((root / "Projects/Aurum/future-branches.json").read_text())
            self.assertFalse(result["fallback_provenance_current"])
            self.assertFalse(result["fallback_warm_current"])
            self.assertFalse(branch["live_controls"]["fallback_carrier_current"])
            self.assertIn("historical only", branch["likely_user_inputs"][0]["prepared_response"])

    def test_new_provenance_head_waits_for_same_head_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.setup_state(root, provenance_head="d" * 40, matrix_head="b" * 40)
            result = sync_fallback_evidence(root)
            branch = json.loads((root / "Projects/Aurum/future-branches.json").read_text())
            self.assertTrue(result["fallback_provenance_current"])
            self.assertFalse(result["fallback_same_head"])
            self.assertFalse(result["fallback_warm_current"])
            self.assertIn("same-head fallback build/boot publication is not yet current", branch["likely_user_inputs"][0]["prepared_response"])

    def test_failed_matrix_cannot_be_warm(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.setup_state(root, matrix_success=False)
            result = sync_fallback_evidence(root)
            self.assertFalse(result["fallback_warm_current"])


if __name__ == "__main__":
    unittest.main()
