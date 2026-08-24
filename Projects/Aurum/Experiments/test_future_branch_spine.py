import unittest
from pathlib import Path


class FutureBranchSpineTests(unittest.TestCase):
    def test_current_spine_contains_required_layers(self):
        root = Path(__file__).resolve().parents[3]
        text = (root / "Architecture" / "FutureBranchCurrent.md").read_text(encoding="utf-8").lower()
        required = [
            "reality gap",
            "surprise reserve",
            "stacked gaps",
            "expected-information-value",
            "unattended precompute",
            "execution routes",
            "human/physical blockers stop the effect",
            "last known good",
            "ran != worked",
            "what happens next if this succeeds?",
            "what happens next if it fails?",
        ]
        missing = [item for item in required if item not in text]
        self.assertFalse(missing, f"Future Branch spine missing required layers: {missing}")

    def test_original_architecture_points_to_current_spine(self):
        root = Path(__file__).resolve().parents[3]
        text = (root / "Architecture" / "FutureBranch.md").read_text(encoding="utf-8")
        self.assertIn("FutureBranchCurrent.md", text)

    def test_portable_seed_retains_operating_spine(self):
        root = Path(__file__).resolve().parents[3]
        text = (root / "Prompts" / "FutureBranchSeed.txt").read_text(encoding="utf-8").lower()
        for item in (
            "effect, not analysis/preparation",
            "unknown-unknown reserve",
            "unattended precompute",
            "ran” ≠ “worked",
            "human chooses direction; machine clears the field",
        ):
            self.assertIn(item, text)


if __name__ == "__main__":
    unittest.main()
