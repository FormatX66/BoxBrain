#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import guardian
import recovery_ledger


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
        self.assertEqual(promoted["previous_lkg"], "A")
        self.assertEqual(guardian.ACTIVE_LINK.resolve(), (guardian.SLOTS_ROOT / "B/opt/aurum").resolve())

        restored = guardian.restore_previous("test-request")
        self.assertEqual(restored["active"], "A")
        self.assertEqual(restored["lkg"], "A")
        self.assertEqual(restored["previous_lkg"], "B")
        self.assertEqual(guardian.ACTIVE_LINK.resolve(), (guardian.SLOTS_ROOT / "A/opt/aurum").resolve())

    def test_failed_candidate_rolls_back_to_lkg(self) -> None:
        guardian.initialize("A")
        bad = guardian.SLOTS_ROOT / "B/opt/aurum/aurum_console.py"
        bad.write_text("def selftest():\n    return False, 'broken'\n", encoding="utf-8")
        guardian.arm_trial(
            "B",
            commit="b" * 40,
            genetics_commit="e" * 40,
            manifest_identity="aurum-genetics-v1:1:fixture",
        )
        guardian.preflight()
        result = guardian.health_check()
        self.assertEqual(result["status"], "rollback")
        self.assertEqual(result["active"], "A")
        self.assertEqual(result["lkg"], "A")
        self.assertEqual(guardian.ACTIVE_LINK.resolve(), (guardian.SLOTS_ROOT / "A/opt/aurum").resolve())
        quarantine = result["quarantined"][-1]
        self.assertEqual(quarantine["genetics_commit"], "e" * 40)
        self.assertEqual(quarantine["manifest_identity"], "aurum-genetics-v1:1:fixture")

    def test_boot_loop_limit_rolls_back(self) -> None:
        guardian.initialize("A")
        guardian.arm_trial("B", commit="c" * 40)
        for _ in range(guardian.MAX_TRIAL_BOOTS):
            self.assertEqual(guardian.preflight()["status"], "trial")
        self.assertEqual(guardian.preflight()["status"], "rollback")
        self.assertEqual(guardian.load_state()["active"], "A")

    def test_checkpoints_and_journal_form_a_valid_hash_chain(self) -> None:
        guardian.initialize("A")
        guardian.arm_trial(
            "B",
            commit="a" * 40,
            genetics_commit="f" * 40,
            manifest_identity="aurum-genetics-v1:1:fixture",
        )
        records = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((guardian.STATE_ROOT / "journal").glob("*.json"))
        ]
        self.assertGreaterEqual(len(records), 4)
        previous = None
        for record in records:
            digest = record.pop("record_sha256")
            self.assertEqual(record["previous_record_sha256"], previous)
            self.assertEqual(hashlib.sha256(recovery_ledger.canonical_json(record)).hexdigest(), digest)
            checkpoint = record.get("checkpoint")
            if checkpoint:
                path = Path(checkpoint["path"])
                self.assertTrue(path.is_file())
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), checkpoint["sha256"])
            previous = digest
        head = json.loads((guardian.STATE_ROOT / "journal-head.json").read_text(encoding="utf-8"))
        self.assertEqual(head["record_sha256"], previous)

    def test_damaged_journal_cannot_block_lkg_rollback(self) -> None:
        guardian.initialize("A")
        guardian.arm_trial("B", commit="c" * 40)
        guardian.preflight()
        (guardian.STATE_ROOT / "journal-head.json").write_text("not-json\n", encoding="utf-8")

        rolled = guardian.rollback("damaged-ledger-test")

        self.assertEqual(rolled["active"], "A")
        self.assertEqual(rolled["lkg"], "A")
        self.assertEqual(guardian.ACTIVE_LINK.resolve(), (guardian.SLOTS_ROOT / "A/opt/aurum").resolve())

    def test_tampered_journal_blocks_forward_mutation(self) -> None:
        guardian.initialize("A")
        head = json.loads((guardian.STATE_ROOT / "journal-head.json").read_text(encoding="utf-8"))
        record_path = Path(head["record"])
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["outcome"] = "tampered"
        record_path.write_text(json.dumps(record), encoding="utf-8")

        with self.assertRaises(guardian.GuardianError):
            guardian.arm_trial("B", commit="d" * 40)

        self.assertIsNone(guardian.load_state()["trial"])
        self.assertEqual(guardian.load_state()["lkg"], "A")


if __name__ == "__main__":
    unittest.main()
