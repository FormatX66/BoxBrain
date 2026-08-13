import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "installer"))
from inspect_aurum_local_lane_approval import codelation_tree_hash, inspect, sha256_file


class LocalLaneApprovalTests(unittest.TestCase):
    def make_repo(self, root: Path):
        (root / "Projects/Codelation/sub").mkdir(parents=True)
        (root / "installer/aurum-local-lane").mkdir(parents=True)
        (root / "Projects/Codelation/a.py").write_text("a=1\n", encoding="utf-8")
        (root / "Projects/Codelation/sub/b.txt").write_text("b\n", encoding="utf-8")
        (root / "installer/deploy-aurum-live-to-pi.ps1").write_text("deploy\n", encoding="utf-8")
        (root / "installer/aurum-local-lane/watch-aurum-local-lane.ps1").write_text("watch\n", encoding="utf-8")

    def config(self, root: Path):
        return {
            "schema_version": 1,
            "repository_root": str(root),
            "approved_commit": "abc",
            "approved_deployer_sha256": sha256_file(root / "installer/deploy-aurum-live-to-pi.ps1"),
            "approved_codelation_tree_sha256": codelation_tree_hash(root),
            "approved_watcher_sha256": sha256_file(root / "installer/aurum-local-lane/watch-aurum-local-lane.ps1"),
        }

    def test_current_approval(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_repo(root)
            result = inspect(self.config(root))
            self.assertTrue(result["approval_current"])
            self.assertEqual([], result["drift"])
            self.assertTrue(result["read_only"])

    def test_codelation_drift_is_reported(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_repo(root)
            config = self.config(root)
            (root / "Projects/Codelation/a.py").write_text("a=2\n", encoding="utf-8")
            result = inspect(config)
            self.assertEqual(["codelation_tree_sha256"], result["drift"])
            self.assertTrue(result["reapproval_required"])

    def test_multiple_drift_components_are_reported(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_repo(root)
            config = self.config(root)
            (root / "installer/deploy-aurum-live-to-pi.ps1").write_text("changed\n", encoding="utf-8")
            (root / "installer/aurum-local-lane/watch-aurum-local-lane.ps1").write_text("changed\n", encoding="utf-8")
            result = inspect(config)
            self.assertEqual(["deployer_sha256", "watcher_sha256"], result["drift"])

    def test_hash_is_path_and_content_deterministic(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            first, second = Path(a), Path(b)
            self.make_repo(first)
            self.make_repo(second)
            self.assertEqual(codelation_tree_hash(first), codelation_tree_hash(second))


if __name__ == "__main__":
    unittest.main()
