from __future__ import annotations

import json
import unittest
from pathlib import Path


POLICY = Path(__file__).parents[1] / "autobuild" / "machine_substrate_policy.json"


class MachineSubstratePolicyTests(unittest.TestCase):
    def test_policy_keeps_capability_above_carrier(self) -> None:
        data = json.loads(POLICY.read_text(encoding="utf-8"))
        self.assertEqual(data["principle"], "capability-before-carrier")
        self.assertIn("missing-product-is-not-a-fundamental-blocker", data["rules"])
        self.assertIn("schedule-by-capability-not-by-host-name", data["rules"])
        self.assertFalse(data["state_direction"]["git_required_for-internal-object-semantics"])
        self.assertTrue(data["runtime_direction"]["scheduler_must_not_depend_on_executor_language"])
        self.assertEqual(data["state_direction"]["mutable_surface"], "refs-only")


if __name__ == "__main__":
    unittest.main()
