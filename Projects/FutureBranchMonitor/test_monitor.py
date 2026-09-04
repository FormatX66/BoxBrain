import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from monitor import Journal, SCHEMA, sample_engine


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.journal = Journal(Path(self.temp.name) / "journal.sqlite3")
        self.report = dict(schema=SCHEMA, thread_id="a", operation_id="build", phase="checking",
                           summary="Check before release", candidates=["test", "hold"], selected="test",
                           evidence=["test result reference"], recovery="Keep previous release")

    def test_reports_do_not_fabricate_coverage_or_independent_verification(self):
        self.journal.context({"tasks": [{"id": t, "title": t, "status": "active"} for t in ["a", "b"]]})
        self.journal.record(self.report)
        data = self.journal.read()
        self.assertEqual(["reported", "unobserved"], [t["coverage"] for t in data["coverage"]])
        self.assertEqual("self_reported", data["chat_reports"][0]["source"])
        self.assertEqual("stale_report", self.journal.read(time.time()+1801)["coverage"][0]["coverage"])
        self.assertTrue(self.journal.read(time.time()+601)["task_inventory"]["stale"])

    def test_duplicate_reports_do_not_refresh_activity(self):
        self.assertTrue(self.journal.record(self.report)["recorded"])
        before = self.journal.read()["chat_reports"][0]["received_at"]
        self.assertFalse(self.journal.record({**self.report, "timestamp": time.time(), "source": "verified"})["recorded"])
        after = self.journal.read()["chat_reports"]
        self.assertEqual(1, len(after))
        self.assertEqual(before, after[0]["received_at"])

    def test_invalid_report_is_rejected(self):
        for change in [{"phase": "verified"}, {"candidates": ["one"]}, {"selected": "missing"}, {"summary": "x"*501}]:
            with self.assertRaises(ValueError):
                self.journal.record({**self.report, **change})

    def test_app_long_titles_remain_verbatim(self):
        title = "Long app-supplied task title " * 70
        self.journal.context({"tasks": [{"id": "a", "title": title, "status": "active"}]})
        self.assertEqual(title.strip(), self.journal.read()["coverage"][0]["title"])

    def test_idle_and_source_failure_are_distinct(self):
        self.journal.snapshot("engine", {"reachable": True, "activity": "idle", "status": "healthy"})
        self.assertEqual("idle", self.journal.read()["engine"]["activity"])
        with patch("monitor.build_opener") as opener:
            opener.return_value.open.side_effect = OSError("private path")
            sample_engine(self.journal)
        data = self.journal.read()["engine"]
        self.assertFalse(data["reachable"])
        self.assertNotIn("activity", data)
        self.assertNotIn("private path", json.dumps(data))
        self.assertTrue(self.journal.read(time.time()+16)["engine"]["stale"])


if __name__ == "__main__":
    unittest.main()
