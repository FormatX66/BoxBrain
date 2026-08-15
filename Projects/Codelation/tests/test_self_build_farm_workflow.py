from __future__ import annotations

import re
import unittest
from pathlib import Path


class SelfBuildFarmWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = (
            Path(__file__).resolve().parents[3]
            / ".github"
            / "workflows"
            / "aurum-self-build-farm.yml"
        ).read_text(encoding="utf-8")

    def test_farm_uses_both_native_linux_architectures_and_ten_workers(self) -> None:
        self.assertIn("runner: ubuntu-24.04\n            arch: x86_64", self.workflow)
        self.assertIn("runner: ubuntu-24.04-arm\n            arch: aarch64", self.workflow)
        self.assertIn("max-parallel: 10", self.workflow)
        self.assertIn("shard: [0, 1, 2, 3, 4]", self.workflow)

    def test_farm_converges_all_lanes_without_repository_write_permission(self) -> None:
        self.assertIn("Converge all architecture lanes", self.workflow)
        self.assertIn("converge_self_build_farm.py", self.workflow)
        self.assertIn('export AURUM_EXPECTED_LANES="${#lane_names[@]}"', self.workflow)
        self.assertIn("expected_gap_count = len(native_semantic_gap_names())", self.workflow)
        self.assertIn("expected_lane_count = expected_gap_count * len(manifest.get('architectures', []))", self.workflow)
        self.assertNotIn("len(states) != 4", self.workflow)
        self.assertNotIn("lane_count') != 40", self.workflow)
        self.assertIn("github.head_ref || github.ref_name", self.workflow)
        self.assertRegex(self.workflow, r"permissions:\s+contents: read")
        self.assertNotRegex(self.workflow, r"permissions:\s+contents: write")


if __name__ == "__main__":
    unittest.main()
