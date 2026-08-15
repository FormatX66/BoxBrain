from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from Projects.Codelation.autobuild import converge_self_build_farm as farm


class SelfBuildFarmConvergenceTests(unittest.TestCase):
    def _lane(self, gap: str) -> dict:
        return {
            "schema": farm.STATE_SCHEMA,
            "catalog_revision": farm.CATALOG_REVISION,
            "synthesis_revision": farm.SYNTHESIS_REVISION,
            "self_debug_revision": farm.SELF_DEBUG_REVISION,
            "local_verification_revision": farm.LOCAL_VERIFICATION_REVISION,
            "start_gap": gap,
            "completed_generations": 1,
            "latest_completed_gap": gap,
            "next_gap": "next_gap",
            "blocked_reason": "generation-bound-reached",
            "reasoning_required": False,
            "generations": [{"generation": 1, "gap": gap}],
        }

    def _write_lane(self, root: Path, arch: str, gap: str, lane: dict) -> None:
        path = root / arch / f"{gap}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(lane), encoding="utf-8")

    def test_matching_architecture_lanes_converge(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for gap in ("alpha", "beta"):
                lane = self._lane(gap)
                self._write_lane(root, "x86_64", gap, lane)
                self._write_lane(root, "aarch64", gap, lane)

            manifest = farm.converge_lanes(root, expected_gaps=("alpha", "beta"))

        self.assertEqual(manifest["lane_count"], 4)
        self.assertEqual(manifest["cross_architecture_determinism"], "verified")
        self.assertEqual([item["start_gap"] for item in manifest["results"]], ["alpha", "beta"])

    def test_architecture_divergence_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            x64 = self._lane("alpha")
            arm64 = self._lane("alpha")
            arm64["next_gap"] = "different"
            self._write_lane(root, "x86_64", "alpha", x64)
            self._write_lane(root, "aarch64", "alpha", arm64)

            with self.assertRaisesRegex(farm.FarmConvergenceError, "divergence"):
                farm.converge_lanes(root, expected_gaps=("alpha",))


if __name__ == "__main__":
    unittest.main()
