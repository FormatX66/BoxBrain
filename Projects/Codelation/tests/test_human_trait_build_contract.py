import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "aurum-human-traits.yml"
RUNTIME = ROOT / "Projects" / "AurumTraits" / "aurum_traits.py"


class HumanTraitBuildContractTests(unittest.TestCase):
    def test_parallel_lanes_build_and_publish_real_artifacts(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        for trait in (
            "TR8:WEB",
            "TR8:FILES",
            "TR8:MEDIA",
            "TR8:WRITE",
            "TR8:INTENT",
            "TR8:CONNECT",
            "TR8:RECOVER",
        ):
            self.assertIn(trait, text)
        self.assertIn("aurum_traits.py build", text)
        self.assertIn("aurum_traits.py verify-bundle", text)
        self.assertIn("actions/upload-artifact@v4", text)
        self.assertIn("aurum-human-traits-seed-payload", text)
        self.assertIn("complete_seed_runtime=true", text)
        self.assertNotIn("stage=contract", text)

    def test_runtime_contains_executable_capability_behavior(self):
        text = RUNTIME.read_text(encoding="utf-8")
        for behavior in (
            "def build_trait(",
            "def verify_bundle(",
            "def materialize_garden(",
            "def resolve_intent(",
            "def recovery_status(",
            "def launch_plan(",
            "subprocess.Popen",
            '"Documents"',
            '"Photos"',
            '"Music"',
            '"Videos"',
        ):
            self.assertIn(behavior, text)
        self.assertIn('"shell_execution": False', text)


if __name__ == "__main__":
    unittest.main()
