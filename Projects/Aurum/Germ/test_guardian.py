#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import guardian


class GuardianTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.old = (guardian.STATE_ROOT, guardian.SLOTS_ROOT, guardian.ACTIVE_LINK, guardian.STATE_FILE)
        guardian.STATE_ROOT = root / "germ"
        guardian.SLOTS_ROOT = root / "slots"
        guardian.ACTIVE_LINK = root / "opt/aurum"
        guardian.STATE_FILE = guardian.STATE_ROOT / "slots.json"
        for slot in ("A", "B"):
            runtime = guardian.SLOTS_ROOT / slot / "opt/aurum"
            runtime.mkdir(parents=True)
            (runtime / "aurum_console.py").write_text(
                "def selftest():\n    return True, 'fixture-ok'\n",
                encoding="utf-8",
            )

    def tearDown(self) -> None:
        guardian.STATE_ROOT, guardian.SLOTS_ROOT, guardian.ACTIVE_LINK, guardian.STATE_FILE = self.old
        self.temp.cleanup()

    def test_trial_promotes_only_after_health(self) -> None:
        state = guardian.initialize("A")
        self.assertEqual(state["lkg"], "A")
        guardian.arm_trial("B", commit="a" * 40)
        trial = guardian.preflight()
        self.assertEqual(trial["status"], "trial")
        before = guardian.load_state()
        self.assertEqual(before["lkg"], "A")
        promoted = guardian.health_check()
        self.assertEqual(promoted["status"], "promoted")
        self.assertEqual(promoted["lkg"], "B")
        self.assertEqual(guardian.ACTIVE_LINK.resolve(), (guardian.SLOTS_ROOT / "B/opt/aurum").resolve())

    def test_failed_candidate_rolls_back_to_lkg(self) -> None:
        guardian.initialize("A")
        bad = guardian.SLOTS_ROOT / "B/opt/aurum/aurum_console.py"
        bad.write_text("def selftest():\n    return False, 'broken'\n", encoding="utf-8")
        guardian.arm_trial("B", commit="b" * 40)
        guardian.preflight()
        result = guardian.health_check()
        self.assertEqual(result["status"], "rollback")
        self.assertEqual(result["active"], "A")
        self.assertEqual(result["lkg"], "A")
        self.assertEqual(guardian.ACTIVE_LINK.resolve(), (guardian.SLOTS_ROOT / "A/opt/aurum").resolve())

    def test_boot_loop_limit_rolls_back(self) -> None:
        guardian.initialize("A")
        guardian.arm_trial("B", commit="c" * 40)
        for _ in range(guardian.MAX_TRIAL_BOOTS):
            self.assertEqual(guardian.preflight()["status"], "trial")
        self.assertEqual(guardian.preflight()["status"], "rollback")
        self.assertEqual(guardian.load_state()["active"], "A")


if __name__ == "__main__":
    unittest.main()
