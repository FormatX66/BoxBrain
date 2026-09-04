import json
import tempfile
import unittest
import urllib.request
import urllib.error
from contextlib import closing
from pathlib import Path

from aurum_farmer.api import FarmerApiServer, serve_in_thread
from aurum_farmer.ledger import Ledger, LedgerError
from aurum_farmer.models import BranchSpec, JobSpec, EvidenceRequirement
from aurum_farmer.telemetry import monitor_snapshot


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.temp.name) / "ledger.db")
        self.ledger.submit(JobSpec(goal="private goal", context={"credential": "private-context"}, branches=(
            BranchSpec(id="private-label", label="private-label", executor="noop", payload={"token": "private-token"},
                       expected_evidence=(EvidenceRequirement("noop_verified"),)),)))
        self.ledger.explore()

    def tearDown(self):
        self.temp.cleanup()

    def test_projection_is_redacted_and_observing_does_not_execute_or_add_decisions(self):
        before = self.ledger.future_status()["decisions"]
        snapshot = monitor_snapshot(self.ledger)
        raw = json.dumps(snapshot)
        for private in ("private-label", "private-token", "private-context", "private goal", str(self.ledger.path)):
            self.assertNotIn(private, raw)
        self.assertEqual(snapshot["activity"], "idle")
        self.assertEqual(snapshot["running_attempts"], 0)
        self.assertTrue(snapshot["recent_decisions"][0]["seal_valid"])
        self.assertIsNotNone(snapshot["recent_decisions"][0]["observed_at"])
        self.assertEqual(snapshot["recent_decisions"][0]["branches"][0]["label"], "Branch 1")
        self.assertEqual(self.ledger.future_status()["decisions"], before)

    def test_bad_seal_is_not_published_as_verified(self):
        with closing(self.ledger._connect()) as con:
            con.execute("DROP TRIGGER future_decisions_no_update")
            con.execute("UPDATE future_decisions SET signature='forged'")
        with self.assertRaises(LedgerError):
            monitor_snapshot(self.ledger)

    def test_loopback_projection_does_not_open_full_job_or_decision_access(self):
        server = FarmerApiServer(("127.0.0.1", 0), self.ledger, "test-token")
        thread = serve_in_thread(server)
        base = "http://127.0.0.1:" + str(server.server_address[1])
        try:
            with urllib.request.urlopen(base + "/monitor") as response:
                self.assertEqual(json.load(response)["schema"], "aurum.future-branch.monitor.v1")
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(urllib.request.Request(base + "/monitor", headers={"Host": "foreign.example"}))
            self.assertEqual(error.exception.code, 403)
            for path in ("/jobs", "/futures"):
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(base + path)
                self.assertEqual(error.exception.code, 401)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)
