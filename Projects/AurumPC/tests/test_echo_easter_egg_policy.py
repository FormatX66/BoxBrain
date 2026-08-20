from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
POLICY_PATH = ROOT / "pc01_autonomy_policy.json"
EASTER_EGG_PATH = ROOT / "ECHO_RALLY_EASTER_EGG.md"


class EchoEasterEggPolicyTests(unittest.TestCase):
    def test_echo_is_not_an_unattended_startup_surface(self) -> None:
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        self.assertIs(policy.get("auto_local_echo_display"), False)

    def test_preservation_contract_keeps_echo_manual(self) -> None:
        contract = EASTER_EGG_PATH.read_text(encoding="utf-8")
        self.assertIn("rather than becoming normal startup behavior", contract)
        self.assertIn("original first-playable Echo Rally build", contract)


if __name__ == "__main__":
    unittest.main()
