from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from aurum_release_gate import (
    GateValidationError,
    REQUIRED_EVIDENCE,
    canonical_sha256,
    converge_evidence,
    evidence_document,
    validate_update_manifest_gate,
)


class AurumReleaseGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.commit = "1" * 40
        self.evidence = [evidence_document(name, self.commit) for name in REQUIRED_EVIDENCE]

    def test_exact_four_target_same_commit_evidence_converges(self) -> None:
        proof = converge_evidence(self.evidence, self.commit)
        self.assertEqual(proof["status"], "verified")
        self.assertEqual(set(proof["required_targets"]), set(REQUIRED_EVIDENCE))
        self.assertEqual(
            proof["evidence_labels"]["qemu_pi3"], "virtual-machine-runtime-proof"
        )
        self.assertEqual(
            proof["evidence_labels"]["physical_hardware"], "not-proven-or-implied"
        )

    def test_mixed_commit_evidence_is_rejected(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence[0]["commit"] = "2" * 40
        with self.assertRaisesRegex(GateValidationError, "different commit"):
            converge_evidence(evidence, self.commit)

    def test_missing_target_is_rejected(self) -> None:
        with self.assertRaisesRegex(GateValidationError, "missing verification targets"):
            converge_evidence(self.evidence[:-1], self.commit)

    def test_qemu_pi3_physical_claim_is_rejected(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence[-1]["physical_hardware_evidence"] = "verified"
        with self.assertRaisesRegex(GateValidationError, "must not claim physical hardware proof"):
            converge_evidence(evidence, self.commit)

    def test_manifest_binds_proof_digest_and_source_commit(self) -> None:
        proof = converge_evidence(self.evidence, self.commit)
        manifest = {
            "source_commit": self.commit,
            "verification": {
                "convergence": proof,
                "convergence_sha256": canonical_sha256(proof),
            },
        }
        self.assertEqual(validate_update_manifest_gate(manifest)["commit"], self.commit)
        manifest["verification"]["convergence_sha256"] = "0" * 64
        with self.assertRaisesRegex(GateValidationError, "digest is invalid"):
            validate_update_manifest_gate(manifest)


if __name__ == "__main__":
    unittest.main()
