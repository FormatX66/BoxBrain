import unittest
from pathlib import Path


class AurumSyncRecoveryContractTests(unittest.TestCase):
    def test_helper_preserves_dirty_workspace_without_hard_reset(self):
        helper = Path(__file__).resolve().parents[1] / "aurum_sync_recovery.py"
        self.assertTrue(helper.is_file())
        text = helper.read_text(encoding="utf-8")
        self.assertIn('stash", "push", "-u"', text)
        self.assertIn('merge", "--ff-only"', text)
        self.assertIn("checkpoint_preserved", text)
        self.assertIn("checkpoint_reapplied", text)
        self.assertIn("apply_updated_runtime", text)
        self.assertIn('"aurum_runtime_update.py"', text)
        self.assertIn('"apply"', text)
        self.assertIn('"runtime_apply"', text)
        self.assertNotIn('reset", "--hard"', text)
        self.assertNotIn('checkout", "-f"', text)

    def test_helper_refuses_wrong_origin_and_branch(self):
        helper = Path(__file__).resolve().parents[1] / "aurum_sync_recovery.py"
        text = helper.read_text(encoding="utf-8")
        self.assertIn("unexpected-origin", text)
        self.assertIn("unexpected-branch", text)


if __name__ == "__main__":
    unittest.main()
