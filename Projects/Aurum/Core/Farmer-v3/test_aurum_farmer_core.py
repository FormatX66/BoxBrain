import json
import socket
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path

from aurum_hive import AurumHive
from aurum_worker import FarmerWorker, audit_completion, choose_future_work


def make_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE objects(id BLOB PRIMARY KEY, kind TEXT, payload BLOB, updated INTEGER);
        CREATE TABLE tags(object_id BLOB, tag TEXT);
        CREATE TABLE hive_nodes(node_id TEXT PRIMARY KEY,name TEXT,capabilities TEXT,last_seen INTEGER);
        CREATE TABLE hive_events(event_id TEXT PRIMARY KEY,origin_node TEXT,event_type TEXT,object_id TEXT,payload BLOB,created INTEGER);
        CREATE TABLE hive_receipts(node_id TEXT,event_id TEXT,status TEXT,processed INTEGER,PRIMARY KEY(node_id,event_id));
        """
    )
    con.commit()
    con.close()


def insert_directive(path: Path, payload: dict, ident: bytes) -> None:
    con = sqlite3.connect(path)
    con.execute(
        "INSERT INTO objects(id,kind,payload,updated) VALUES(?,?,?,?)",
        (ident, "directive", json.dumps(payload).encode(), int(time.time())),
    )
    con.execute("INSERT INTO tags(object_id,tag) VALUES(?,?)", (ident, "directive"))
    con.commit()
    con.close()


SAFE = {
    "authority": "authorized",
    "reversibility": "full",
    "fresh": True,
    "confidence": 0.9,
    "evidence_quality": 0.9,
    "risk": 0.1,
    "cost": 0.1,
    "impact": 0.9,
}


class FarmerCoreTests(unittest.TestCase):
    def test_failed_tool_cannot_replay_under_new_directive_after_restart(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "slush.db"
            make_db(db)
            calls = []
            def fail(parameters):
                calls.append(parameters)
                return {"status": "failed", "human_required": False}
            payload = {"action": "run_checks", "parameters": {"name": "python-unittest"}}
            first = FarmerWorker(db, root / "worker.sock", root)
            first._tools["run_checks"] = fail
            self.assertEqual(first.process_slush_directive("first", payload)["status"], "failed")
            restarted = FarmerWorker(db, root / "worker.sock", root)
            restarted._tools["run_checks"] = fail
            self.assertEqual(restarted.process_slush_directive("second", payload)["status"], "waiting")
            self.assertEqual(len(calls), 1)
            payload["parameters"]["name"] = "python-pytest"
            self.assertEqual(restarted.process_slush_directive("third", payload)["status"], "failed")
            self.assertEqual(len(calls), 2)

    def test_common_dispatch_records_decision_and_calibrated_outcome(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "slush.db"
            make_db(db)
            worker = FarmerWorker(db, root / "worker.sock", root)
            result = worker._dispatch("echo", {"message": "engine-proof"})
            self.assertEqual(result["status"], "succeeded")
            con = sqlite3.connect(db)
            try:
                events = dict(con.execute("SELECT event_type,payload FROM farmer_events"))
            finally:
                con.close()
            decision = json.loads(events["future_branch_decision"])
            self.assertEqual(decision["schema"], "aurum.future-branch.decision.v1")
            self.assertGreater(len(decision["nodes"]), 10)
            outcome = json.loads(events["future_branch_outcome"])
            self.assertEqual(outcome["state_id"], decision["state_id"])
            self.assertAlmostEqual(outcome["brier"], .04)
            self.assertFalse(outcome["lkg_promoted"])

    def test_high_risk_future_is_not_automatically_promoted(self):
        result = choose_future_work({"branches": [{"id": "unsafe", **SAFE, "risk": .9}]})
        self.assertIsNone(result["promoted_branch"])

    def test_completion_definition_is_strict(self):
        complete = audit_completion(
            {
                "no_further_human_input": True,
                "no_known_bugs_or_glitches": True,
                "fully_functional": True,
                "no_required_changes_remaining": True,
                "verification_passed": True,
            }
        )
        self.assertTrue(complete["complete"])
        self.assertEqual(complete["terminal_state"], "verified_completion")
        incomplete = audit_completion({"fully_functional": True})
        self.assertFalse(incomplete["complete"])
        self.assertFalse(incomplete["terminal"])

    def test_only_proven_human_blocker_is_terminal(self):
        machine = audit_completion({"blocker": {"kind": "github_connector_missing"}})
        self.assertFalse(machine["terminal"])
        self.assertFalse(machine["blocker"]["human_required"])
        human = audit_completion({"blocker": {"kind": "physical_intervention"}})
        self.assertTrue(human["terminal"])
        self.assertEqual(human["terminal_state"], "proven_human_only_blocker")

    def test_future_branch_rejects_irreversible_candidate(self):
        result = choose_future_work(
            {
                "last_known_good": "safe",
                "branches": [
                    {"id": "unsafe", **SAFE, "confidence": 1.0, "reversibility": "none"},
                    {"id": "safe", **SAFE},
                ],
            }
        )
        self.assertEqual(result["promoted_branch"]["id"], "safe")
        self.assertEqual(result["last_known_good"], "safe")

    def test_worker_drains_all_slush_directives(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "slush.db"
            make_db(db)
            insert_directive(db, {"action": "echo", "parameters": {"message": "one"}}, b"directive-000001")
            insert_directive(db, {"action": "echo", "parameters": {"message": "two"}}, b"directive-000002")
            worker = FarmerWorker(db, root / "worker.sock", root)
            results = worker.drain()
            self.assertEqual(len([r for r in results if "directive_id" in r]), 2)
            con = sqlite3.connect(db)
            count = con.execute("SELECT count(*) FROM farmer_receipts").fetchone()[0]
            con.close()
            self.assertEqual(count, 2)

    def test_everything_all_at_once_runs_independent_safe_work(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "slush.db"
            make_db(db)
            worker = FarmerWorker(db, root / "worker.sock", root)
            result = worker._tool_farmer_plan(
                {
                    "completion": {},
                    "work_items": [
                        {"id": "a", "action": "echo", "parameters": {"message": "A"}, **SAFE},
                        {"id": "b", "action": "echo", "parameters": {"message": "B"}, **SAFE},
                    ],
                }
            )
            self.assertEqual(result["status"], "machine_blocked")
            self.assertEqual({r["id"] for r in result["results"]}, {"a", "b"})
            self.assertFalse(result["human_required"])

    def test_plan_loops_dependencies_until_verified_completion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "slush.db"
            make_db(db)
            worker = FarmerWorker(db, root / "worker.sock", root)
            final_updates = {
                "no_further_human_input": True,
                "no_known_bugs_or_glitches": True,
                "fully_functional": True,
                "no_required_changes_remaining": True,
                "verification_passed": True,
            }
            result = worker._tool_farmer_plan(
                {
                    "completion": {},
                    "work_items": [
                        {
                            "id": "build",
                            "action": "echo",
                            "parameters": {"message": "build"},
                            "success_updates": {"fully_functional": True},
                            **SAFE,
                        },
                        {
                            "id": "verify",
                            "depends_on": ["build"],
                            "action": "echo",
                            "parameters": {"message": "verify"},
                            "success_updates": final_updates,
                            **SAFE,
                        },
                    ],
                }
            )
            self.assertEqual(result["status"], "verified_completion")
            self.assertTrue(result["audit"]["complete"])
            self.assertEqual([r["id"] for r in result["results"]], ["build", "verify"])

    def test_failed_primary_activates_safe_fallback_without_user(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "slush.db"
            make_db(db)
            worker = FarmerWorker(db, root / "worker.sock", root)
            final_updates = {
                "no_further_human_input": True,
                "no_known_bugs_or_glitches": True,
                "fully_functional": True,
                "no_required_changes_remaining": True,
                "verification_passed": True,
            }
            result = worker._tool_farmer_plan(
                {
                    "completion": {},
                    "work_items": [
                        {"id": "primary", "action": "not-a-real-tool", **SAFE},
                        {
                            "id": "fallback",
                            "fallback_for": "primary",
                            "action": "echo",
                            "parameters": {"message": "fallback"},
                            "success_updates": final_updates,
                            **SAFE,
                        },
                    ],
                }
            )
            self.assertEqual(result["status"], "verified_completion")
            self.assertEqual([r["id"] for r in result["results"]], ["primary", "fallback"])
            self.assertFalse(result["human_required"])

    def test_quarantined_primary_still_activates_recovery(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "slush.db"
            make_db(db)
            worker = FarmerWorker(db, root / "worker.sock", root)
            worker._tools["run_checks"] = lambda p: {"status": "failed", "human_required": False}
            worker._dispatch("run_checks", {"name": "python-unittest"})
            result = worker._tool_farmer_plan({"work_items": [
                {"id": "primary", "action": "run_checks", "parameters": {"name": "python-unittest"}, **SAFE},
                {"id": "fallback", "fallback_for": "primary", "action": "echo", **SAFE}]})
            self.assertEqual([r["id"] for r in result["results"]], ["primary", "fallback"])
            self.assertTrue(result["results"][0]["quarantined"])
            self.assertEqual(result["results"][1]["status"], "succeeded")

    def test_hive_farmer_directive_is_consumed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "slush.db"
            make_db(db)
            worker = FarmerWorker(db, root / "worker.sock", root)
            con = sqlite3.connect(db)
            payload = {"farmer_directive": {"action": "echo", "parameters": {"message": "from-hive"}}}
            con.execute(
                "INSERT INTO hive_events(event_id,origin_node,event_type,object_id,payload,created) VALUES(?,?,?,?,?,?)",
                ("evt-1", "remote", "state_delta", None, json.dumps(payload).encode(), int(time.time())),
            )
            con.commit()
            con.close()
            results = worker.drain()
            self.assertTrue(any(r.get("hive_event_id") == "evt-1" and r.get("message") == "from-hive" for r in results))
            con = sqlite3.connect(db)
            receipt = con.execute(
                "SELECT status,human_required FROM farmer_hive_receipts WHERE event_id='evt-1'"
            ).fetchone()
            con.close()
            self.assertEqual(receipt, ("succeeded", 0))

    def test_hive_to_live_worker_acknowledges_drain_and_receipt(self):
        if not hasattr(socket, "AF_UNIX"):
            self.skipTest("AF_UNIX unavailable")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "slush.db"
            sock = root / "worker.sock"
            make_db(db)
            worker = FarmerWorker(db, sock, root)
            thread = threading.Thread(target=worker.serve_forever, daemon=True)
            thread.start()
            deadline = time.time() + 2
            while not sock.exists() and time.time() < deadline:
                time.sleep(0.01)
            self.assertTrue(sock.exists())
            hive = AurumHive("integration-node", ["worker"], db, sock)
            try:
                event_id = hive.publish_delta({
                    "merge_policy": {"require_provenance": True},
                    "farmer_directive": {"action": "echo", "parameters": {"message": "e2e"}},
                })
                self.assertIsNotNone(hive.last_farmer_ack)
                self.assertEqual(hive.last_farmer_ack.get("status"), "drained")
                self.assertGreaterEqual(hive.last_farmer_ack.get("processed", 0), 1)
                con = sqlite3.connect(db)
                receipt = con.execute(
                    "SELECT status,human_required FROM farmer_hive_receipts WHERE event_id=?",
                    (event_id,),
                ).fetchone()
                con.close()
                self.assertEqual(receipt, ("succeeded", 0))
            finally:
                hive.close()
                worker.stop()
                thread.join(2)

    def test_hive_commit_wakes_worker_via_os_event_socket(self):
        if not hasattr(socket, "AF_UNIX"):
            self.skipTest("AF_UNIX unavailable")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "slush.db"
            sock = root / "worker.sock"
            make_db(db)
            received = []
            ready = threading.Event()

            def server():
                srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                srv.bind(str(sock))
                srv.listen(1)
                ready.set()
                conn, _ = srv.accept()
                with conn:
                    received.append(json.loads(conn.recv(4096).decode()))
                srv.close()

            thread = threading.Thread(target=server, daemon=True)
            thread.start()
            self.assertTrue(ready.wait(2))
            hive = AurumHive("test-node", ["worker"], db, sock)
            try:
                hive.publish_delta({"merge_policy": {"require_provenance": True}, "state": "changed"})
            finally:
                hive.close()
            thread.join(2)
            self.assertEqual(received[0]["event"], "hive_delta")


if __name__ == "__main__":
    unittest.main()
