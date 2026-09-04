import dataclasses
import hashlib
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from aurum_farmer.decision_engine import Budget, DecisionEngine, Probe, score
from aurum_farmer.executors import ExecutorRegistry, NoopExecutor
from aurum_farmer.ledger import Ledger, LedgerError
from aurum_farmer.models import BranchSpec, EvidenceItem, EvidenceRequirement, ExecutionResult, JobSpec, Outcome
from aurum_farmer.supervisor import Supervisor
from aurum_farmer.verification import verify_result


def proposal(name="a", **extra):
    return {"id": name, "executor": "noop", "payload": {"marker": name},
            "expected_evidence": [{"kind": "noop_verified"}], "confidence": .9,
            "impact": .9, "evidence_quality": 1, **extra}


class EngineTests(unittest.TestCase):
    def test_formula_and_unmeasured_confidence_cannot_buy_verification(self):
        b = proposal(risk=.1, irreversible_cost=.2, uncertainty=.1)
        self.assertAlmostEqual(score(b, .5), .9 * .9 * .5 - .4)
        report = DecisionEngine().evaluate({}, [proposal(required_tier="vm")])
        self.assertIsNone(report["selected"])
        self.assertEqual(report["branches"][0]["evidence_quality"], .25)

    def test_wide_dag_is_bounded_acyclic_and_holds_lkg(self):
        report = DecisionEngine(budget=Budget(nodes=128)).evaluate({"lkg": {"os": "old"}},
                    [proposal(str(i), confidence=.5 + i / 1000) for i in range(32)])
        self.assertLessEqual(len(report["nodes"]), 128)
        self.assertGreater(len(report["nodes"]), 64)
        seen = set()
        for node in report["nodes"]:
            self.assertTrue(set(node["parents"]) <= seen)
            seen.add(node["id"])
        self.assertEqual(report["nodes"][2]["references"], {"os": "old"})

    def test_prunes_unsafe_impossible_redundant_expired_and_dependency(self):
        branches = [proposal("a"), proposal("copy", payload={"marker": "a"}),
                    proposal("unsafe", risk=.8), proposal("impossible", impossible=True),
                    proposal("expired", expires_at=1), proposal("dependency", dependencies_satisfied=False),
                    proposal("cycle", parents=["cycle"])]
        report = DecisionEngine().evaluate({}, branches)
        self.assertEqual(report["selected"], "a")
        self.assertTrue(all(b["reason"] for b in report["branches"][1:]))

    def test_ambiguous_candidates_wait_without_manufacturing_certainty(self):
        self.assertEqual(DecisionEngine().evaluate({}, [proposal("a"), proposal("b")])["status"], "ambiguous")

    def test_tiers_parallel_budget_failure_and_cache(self):
        lock = threading.Lock()
        active = 0
        peak = 0
        calls = []

        def probe(state, b):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
                calls.append(b["logical_id"])
            time.sleep(.02)
            with lock:
                active -= 1
            return {"passed": b["logical_id"] != "0", "evidence_ref": "measured:" + b["logical_id"]}

        engine = DecisionEngine(budget=Budget(probe_units=8), probes=(Probe("unit", "unit-verifier", probe),
                                                                    Probe("vm", "vm-verifier", probe)))
        branches = [proposal(str(i), confidence=.8 + i / 100) for i in range(4)]
        report = engine.evaluate({}, branches, deepen=True)
        self.assertGreater(peak, 1)
        self.assertLessEqual(report["probe_units"], 8)
        self.assertTrue(report["branches"][0]["reason"].startswith("verification_failed"))
        call_count = len(calls)
        # A fully budgeted cycle may deepen additional survivors next time; already
        # checked branch/tier pairs are never re-run for identical semantic input.
        again = engine.evaluate({}, branches, deepen=False, prior=report)
        self.assertEqual(len(calls), call_count)
        self.assertFalse(again["branches"][0]["automatic"])
        fresh = engine.evaluate({"commit": "changed"}, branches, prior=report)
        self.assertTrue(all(len(b["tests"]) == 1 for b in fresh["branches"]))

    def test_hardware_is_exclusive_and_cannot_skip_unavailable_tier(self):
        calls = []
        engine = DecisionEngine(probes=(Probe("canary", "hardware-verifier", lambda s, b: calls.append(b)),))
        report = engine.evaluate({}, [proposal(required_tier="canary")], deepen=True)
        self.assertFalse(calls)
        self.assertIsNone(report["selected"])

    def test_proposer_cannot_impersonate_verifier_or_relabel_authority(self):
        with self.assertRaises(ValueError):
            DecisionEngine(probes=(Probe("unit", "farmer-executor", lambda s, b: {}),))
        with self.assertRaises(ValueError):
            BranchSpec.from_dict(proposal(decision={"authority_ready": True})).validate()

    def test_mutation_requires_lkg_rollback_and_unit(self):
        b = proposal(effect="reversible", lkg_scope="os", rollback_ref="restore-old")
        engine = DecisionEngine(probes=(Probe("unit", "unit-verifier", lambda s, b:
                                {"passed": True, "rollback_verified": True, "evidence_ref": "unit-test-receipt"}),))
        self.assertIsNone(engine.evaluate({}, [b], deepen=True)["selected"])
        self.assertEqual(engine.evaluate({"lkg": {"os": "old"}}, [b], deepen=True)["selected"], "a")


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ledger = Ledger(self.root / "farmer.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def submit(self, name="a", **kwargs):
        return self.ledger.submit(JobSpec(goal=name, branches=(BranchSpec(
            id=name, label=name, executor="noop", expected_evidence=(EvidenceRequirement("noop_verified"),),
            **kwargs),)))[0]

    def test_every_claim_is_gated_including_direct_ledger_caller(self):
        job = self.submit(risk=.9)
        self.assertIsNone(self.ledger.claim_next("bypass"))
        self.assertFalse(self.ledger.get_job(job)["attempts"])
        self.assertIsNotNone(self.ledger.future_status(job)["latest"])

    def test_quarantine_survives_new_job_id_and_uses_sealed_failure(self):
        first = self.submit("first")
        context = self.ledger.claim_next("worker")
        self.ledger.finish_attempt(context["id"], "worker", ExecutionResult(
            Outcome.FAILED, "broken", failure_class="stable", failure_fingerprint="same"))
        self.ledger = Ledger(self.ledger.path)
        second = self.submit("second")
        self.assertIsNone(self.ledger.claim_next("worker"))
        self.assertFalse(self.ledger.get_job(second)["attempts"])
        changed = self.submit("changed", payload={"marker": "new action"})
        self.assertIsNotNone(self.ledger.claim_next("worker"))
        with closing(self.ledger._connect()) as con:
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("DELETE FROM future_quarantines")
        self.assertTrue(self.ledger.verify_event_chain())

    def test_evidence_resume_cannot_grant_authority_or_clear_human_boundary(self):
        from aurum_farmer.models import HumanBoundary
        job = self.submit(authority_ready=False, human_boundary=HumanBoundary(
            "credential", "sign in", "owner sign-in"))
        self.assertIsNone(self.ledger.claim_next("worker"))
        self.ledger.resume(job, changed_dimension="evidence", note="unrelated evidence")
        self.assertIsNone(self.ledger.claim_next("worker"))
        self.assertFalse(self.ledger.get_job(job)["attempts"])

    def test_binary_signing_key_roundtrips_newlines_after_restart(self):
        with patch("aurum_farmer.ledger.secrets.token_bytes", return_value=b"\n" * 32):
            first = Ledger(self.root / "new.sqlite3")
        reopened = Ledger(first.path)
        self.assertEqual(first._sign("digest"), reopened._sign("digest"))
        self.assertEqual(first.signing_key_path.stat().st_size, 32)

    def test_github_success_requires_independent_matching_run_source(self):
        result = ExecutionResult(Outcome.SUCCEEDED, "executor claims success", evidence=(
            EvidenceItem("github_actions_run", "github", {"databaseId": 42, "headSha": "expected"}),))
        context = {"id": "attempt", "executor": "github_workflow", "payload": {"repository": "owner/repo"}}
        with patch("aurum_farmer.verification.subprocess.run", return_value=SimpleNamespace(stdout=json.dumps(
                {"id": 42, "status": "completed", "conclusion": "success", "head_sha": "different"}))):
            self.assertEqual(verify_result(context, result).outcome, Outcome.FAILED)
        with patch("aurum_farmer.verification.subprocess.run", return_value=SimpleNamespace(stdout=json.dumps(
                {"id": 42, "status": "completed", "conclusion": "success", "head_sha": "expected"}))):
            verified = verify_result(context, result)
            self.assertEqual(verified.outcome, Outcome.SUCCEEDED)
            self.assertEqual(verified.evidence[-1].source, "farmer-result-verifier-v1")

    def test_exploration_observes_new_jobs_during_execution(self):
        ledger = self.ledger
        started = threading.Event()
        observed = threading.Event()
        original = ledger.explore

        def explore():
            count = original()
            if started.is_set() and count > 1:
                observed.set()
            return count

        ledger.explore = explore

        class SlowExecutor(NoopExecutor):
            def execute(inner, context):
                started.set()
                self.submit("arrived-during-execution")
                if not observed.wait(3):
                    raise AssertionError("exploration did not overlap execution")
                return super().execute(context)

        registry = ExecutorRegistry()
        registry.register("noop", SlowExecutor())
        self.submit()
        result = Supervisor(ledger, registry, poll_seconds=.1).tick()
        self.assertEqual(result["job_state"], "SUCCEEDED")
        self.assertTrue(observed.is_set())

    def test_restart_append_only_calibration_and_no_duplicate_exploration(self):
        job = self.submit()
        self.ledger.explore()
        before = self.ledger.future_status()["decisions"]
        self.ledger.explore()
        self.assertEqual(self.ledger.future_status()["decisions"], before)
        reopened = Ledger(self.ledger.path)
        registry = ExecutorRegistry()
        registry.register("noop", NoopExecutor())
        Supervisor(reopened, registry).tick()
        self.assertEqual(reopened.get_job(job)["state"], "SUCCEEDED")
        self.assertEqual(reopened.future_status()["calibrated_outcomes"], 1)
        self.assertAlmostEqual(reopened.future_status()["mean_brier_score"], .25)
        with closing(reopened._connect()) as con:
            for table in ("future_decisions", "future_outcomes"):
                with self.assertRaises(sqlite3.IntegrityError):
                    con.execute("DELETE FROM " + table)
        self.assertTrue(reopened.verify_event_chain())

    def test_forged_success_is_rejected_without_changing_lkg(self):
        job = self.submit(lkg_scope="protected")
        context = self.ledger.claim_next("executor")
        forged = ExecutionResult(Outcome.SUCCEEDED, "trust me", evidence=(
            EvidenceItem("noop_verified", "proposer", {"marker_sha256": "forged"}),), lkg_ref="bad")
        result = self.ledger.finish_attempt(context["id"], "executor", forged)
        self.assertNotEqual(result["state"], "SUCCEEDED")
        self.assertIsNone(self.ledger.last_known_good("protected"))
        self.assertEqual(self.ledger.future_status()["mean_brier_score"], .25)

    def test_tampered_cached_verification_cannot_authorize_execution(self):
        self.submit()
        self.ledger.explore()
        with closing(self.ledger._connect()) as con:
            con.execute("DROP TRIGGER future_decisions_no_update")
            con.execute("UPDATE future_decisions SET report_json='{}'")
        with self.assertRaises(LedgerError):
            self.ledger.claim_next("executor")

    def test_changed_probe_revision_invalidates_old_verification(self):
        first = DecisionEngine(probes=(Probe("unit", "verifier", lambda s, b:
                               {"passed": True, "evidence_ref": "test"}, revision="first"),))
        report = first.evaluate({}, [proposal(required_tier="unit")], deepen=True)
        changed = DecisionEngine(probes=(Probe("unit", "verifier", lambda s, b: {}, revision="changed"),))
        self.assertIsNone(changed.evaluate({}, [proposal(required_tier="unit")], prior=report)["selected"])


if __name__ == "__main__":
    unittest.main()
