from __future__ import annotations

import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[3]


class WorkflowGateContractTests(unittest.TestCase):
    def test_pi_image_workflow_cannot_publish_runtime_update(self) -> None:
        workflow = (REPOSITORY / ".github/workflows/aurum-pi3-v001.yml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("Publish pinned application runtime release", workflow)
        self.assertNotIn("Aurum-Pi3-runtime-${{", workflow)
        self.assertNotIn("--release-id", workflow)

    def test_runtime_promotion_is_downstream_of_same_commit_gate(self) -> None:
        workflow = (REPOSITORY / ".github/workflows/aurum-virtual-lab.yml").read_text(
            encoding="utf-8"
        )
        for job in ("docker-x64:", "docker-arm64:", "qemu-pc:", "qemu-pi3:"):
            self.assertIn(job, workflow)
        gate = workflow.index("  virtual-lab-gate:")
        promotion = workflow.index("  promote-pi3-runtime:")
        self.assertLess(gate, promotion)
        promotion_text = workflow[promotion:]
        self.assertIn("needs:\n      - virtual-lab-gate", promotion_text)
        self.assertIn("--convergence-proof release-input/aurum-convergence-proof.json", promotion_text)
        self.assertIn("gh release create", promotion_text)
        self.assertIn("gh release edit \"$TAG\" --draft=false", promotion_text)


if __name__ == "__main__":
    unittest.main()
