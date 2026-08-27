from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/aurum-tiny-seed-windows-cache-stage.yml"


class TinySeedWindowsCacheNoChangeTests(unittest.TestCase):
    def test_successful_handoff_without_artifact_is_no_change(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        no_change = "AURUM_TINYSEED_CACHE_NO_CHANGE reason=handoff-not-published"
        missing_artifact = "AURUM_TINYSEED_CACHE_REFUSED reason=handoff-artifact-missing"
        self.assertIn(no_change, text)
        self.assertIn(missing_artifact, text)
        self.assertLess(text.index(no_change), text.index(missing_artifact))

    def test_no_change_path_preserves_zero_authority(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        marker = next(line for line in text.splitlines() if "AURUM_TINYSEED_CACHE_NO_CHANGE" in line)
        self.assertIn("destructive_media_write=false", marker)
        self.assertIn("write_authority=false", marker)


if __name__ == "__main__":
    unittest.main()
