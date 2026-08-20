from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "aurum-frontier.yml"


class GateEventChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_virtual_convergence_is_bound_to_exact_semantic_commit(self) -> None:
        self.assertIn("Resolve semantic proof commit", self.workflow)
        self.assertIn("proof_commit=\"$(git rev-list -1 HEAD -- .", self.workflow)
        self.assertIn("native_gate_state.bin", self.workflow)
        self.assertIn("native_gate_projection.json", self.workflow)
        self.assertIn("Aurum-VirtualLab-Convergence-${PROOF_COMMIT}", self.workflow)
        self.assertIn("select(.head_sha == $sha and .conclusion == \"success\")", self.workflow)

    def test_virtual_proof_cannot_claim_physical_hardware_or_authority(self) -> None:
        self.assertIn("'physical_hardware': 'not-proven-or-implied'", self.workflow)
        self.assertIn("'credential_content_captured': False", self.workflow)
        self.assertIn("'authority_granted': False", self.workflow)
        self.assertIn("physical_hardware_not_claimed", self.workflow)
        self.assertIn("no_host_authority", self.workflow)

    def test_missing_virtual_proof_starts_dependency_and_wakes_gate_chain(self) -> None:
        self.assertIn("Request exact-commit virtual convergence when missing", self.workflow)
        self.assertIn("actions/workflows/aurum-virtual-lab.yml/dispatches", self.workflow)
        self.assertIn("wait-for-virtual-convergence:", self.workflow)
        self.assertIn("Wake gate frontier from exact-commit virtual convergence", self.workflow)
        self.assertIn("actions/workflows/aurum-frontier.yml/dispatches", self.workflow)
        self.assertIn("virtual_requested == 'true'", self.workflow)

    def test_machine_state_commits_do_not_redefine_semantic_proof_commit(self) -> None:
        semantic_source = self.workflow.split("Resolve semantic proof commit", 1)[1].split(
            "Bind successful same-commit virtual convergence proof", 1
        )[0]
        self.assertIn("':(exclude)Projects/Codelation/autobuild/native_gate_state.bin'", semantic_source)
        self.assertIn("':(exclude)Projects/Codelation/autobuild/native_gate_projection.json'", semantic_source)
        self.assertIn("git diff --quiet \"$proof_commit\"..HEAD", semantic_source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
