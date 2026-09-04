import json
import sqlite3
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from aurum_farmer.operation_gate import OperationGate, workspace_revision, source_revision


class OperationGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "gate.sqlite3"
        self.gate = OperationGate(self.path, implementation="code-v1")

    def tearDown(self):
        self.temp.cleanup()

    def test_failed_attempt_survives_restart_and_new_transport_id(self):
        ticket = self.gate.begin("test", {"target": "a", "request_id": "one"}, {"revision": "a"})
        self.gate.finish(ticket, "failed", {"secret": "must-not-be-stored"})
        restarted = OperationGate(self.path, implementation="code-v1")
        repeated = restarted.begin("test", {"target": "a", "request_id": "two"}, {"revision": "a"})
        self.assertFalse(repeated["allowed"])
        self.assertEqual(repeated["reason"], "unchanged_failed_operation")
        self.assertNotIn(b"must-not-be-stored", self.path.read_bytes())
        self.assertTrue(restarted.begin("test", {"target": "b"}, {"revision": "a"})["allowed"])
        self.assertTrue(restarted.begin("test", {"target": "a"}, {"revision": "b"})["allowed"])
        self.assertTrue(OperationGate(self.path, implementation="code-v2").begin(
            "test", {"target": "a"}, {"revision": "a"})["allowed"])

    def test_source_observation_ignores_receipts_but_sees_uncommitted_repair(self):
        root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        code = root / "main.py"
        code.write_text("broken = True")
        before = workspace_revision(root)
        (root / "receipt.json").write_text('{"counter": 5}')
        self.assertEqual(workspace_revision(root), before)
        code.write_text("broken = False")
        self.assertNotEqual(workspace_revision(root), before)
        copy = root / "new-release" / "main.py"
        copy.parent.mkdir()
        copy.write_bytes(code.read_bytes())
        self.assertEqual(source_revision([code]), source_revision([copy]))

    def test_parallel_same_operation_has_one_owner_and_crash_does_not_unlock(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            tickets = list(pool.map(lambda _: self.gate.begin("test", {}, {}), range(8)))
        self.assertEqual(sum(t["allowed"] for t in tickets), 1)
        restarted = OperationGate(self.path, implementation="code-v1")
        self.assertFalse(restarted.begin("test", {}, {})["allowed"])

    def test_waiting_and_refusal_are_not_failed_and_recovery_remains_available(self):
        for outcome in ("waiting", "refused", "observed"):
            ticket = self.gate.begin(outcome, {}, {})
            self.gate.finish(ticket, outcome, {})
            self.assertTrue(self.gate.begin(outcome, {}, {})["allowed"])
        ticket = self.gate.begin("probe", {}, {})
        self.gate.finish(ticket, "failed", {})
        self.assertTrue(self.gate.begin("probe", {}, {}, recovery_observation=True)["allowed"])

    def test_stale_finish_cannot_replace_new_owner_and_admission_is_not_success(self):
        first = self.gate.begin("read", {}, {}, recovery_observation=True)
        second = self.gate.begin("read", {}, {}, recovery_observation=True)
        self.gate.finish(first, "failed", {})
        self.gate.finish(second, "observed", {})
        self.assertEqual(self.gate.status()["operations"], {"observed": 1})
        with self.assertRaises(ValueError):
            self.gate.finish(second, "verified_completion", {})
        con = sqlite3.connect(self.path)
        try:
            outcomes = [json.loads(row[0]) for row in con.execute(
                "SELECT payload_json FROM future_operation_events WHERE event='outcome'")]
        finally:
            con.close()
        self.assertTrue(all(not row["lkg_promoted"] and not row["verified_completion"] for row in outcomes))
