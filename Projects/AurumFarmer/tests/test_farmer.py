from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from aurum_farmer.executors import (
    ChatToGitExecutor,
    EvidenceFileExecutor,
    ExecutorRegistry,
    NoopExecutor,
)
from aurum_farmer.ledger import Ledger
from aurum_farmer.models import (
    BranchSpec,
    EvidenceItem,
    EvidenceRequirement,
    ExecutionResult,
    HumanBoundary,
    JobSpec,
    JobState,
    Outcome,
)
from aurum_farmer.supervisor import Supervisor


class StaticExecutor:
    def __init__(self, *results: ExecutionResult):
        self.results = list(results)

    def execute(self, context):
        return self.results.pop(0)


def success(kind: str = "verified_result", *, lkg_ref: str | None = None) -> ExecutionResult:
    return ExecutionResult(
        outcome=Outcome.SUCCEEDED,
        summary="verified",
        evidence=(EvidenceItem(kind=kind, source="test", data={"ok": True}),),
        lkg_ref=lkg_ref,
    )


class FakeGhClient:
    def json(self, args, **kwargs):
        if args[:2] == ["run", "view"]:
            return {
                "databaseId": 42,
                "status": "completed",
                "conclusion": "success",
                "url": "https://github.com/FormatX66/Chat-to-Git-Pipeline/actions/runs/42",
                "headSha": "a" * 40,
                "workflowName": "Voice Chat Pipeline",
                "event": "repository_dispatch",
            }
        raise AssertionError(args)


class FakeChatToGitExecutor(ChatToGitExecutor):
    def __init__(self):
        super().__init__(FakeGhClient())
        self.dispatched = 0

    def _feedback(self, repository, request_id):
        issue = {"number": 9, "html_url": "https://github.com/FormatX66/Chat-to-Git-Pipeline/issues/9"}
        comments = [{
            "body": (
                f"<!-- pipeline-status:{request_id}:succeeded -->\n"
                "https://github.com/FormatX66/Chat-to-Git-Pipeline/actions/runs/42"
            )
        }]
        return (None, []) if self.dispatched == 0 else (issue, comments)

    def _dispatch_primary(self, repository, request):
        self.dispatched += 1

    def _artifact_receipt(self, repository, run_id, request_id):
        return (
            {"schema": "chat-to-git.receipt.v1", "request_id": request_id, "status": "succeeded"},
            "https://api.github.test/artifact/1",
        )


class FarmerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "farmer.sqlite3"
        self.key = self.root / "farmer.key"
        self.ledger = Ledger(self.db, signing_key_path=self.key)

    def tearDown(self):
        self.temp.cleanup()

    def registry(self, name="noop", executor=None):
        registry = ExecutorRegistry()
        registry.register(name, executor or NoopExecutor())
        return registry

    def submit_one(self, *, executor="noop", expected="noop_verified", max_attempts=1, lkg_scope=None):
        return self.ledger.submit(
            JobSpec(
                goal="test durable Farmer behavior",
                branches=(
                    BranchSpec(
                        id="primary",
                        label="primary",
                        executor=executor,
                        expected_evidence=(EvidenceRequirement(expected),),
                        max_attempts=max_attempts,
                        lkg_scope=lkg_scope,
                    ),
                ),
            )
        )[0]

    def test_canary_closes_only_after_signed_evidence_and_preserves_lkg(self):
        job_id = self.ledger.submit(
            JobSpec(
                goal="canary",
                branches=(
                    BranchSpec(
                        id="canary",
                        label="canary",
                        executor="noop",
                        payload={"marker": "proof"},
                        expected_evidence=(EvidenceRequirement("noop_verified"),),
                        lkg_scope="farmer-runtime",
                    ),
                ),
            )
        )[0]
        result = Supervisor(self.ledger, self.registry(), owner="test-supervisor").tick()
        self.assertEqual(result["job_state"], JobState.SUCCEEDED.value)
        job = self.ledger.get_job(job_id)
        self.assertEqual(job["state"], JobState.SUCCEEDED.value)
        self.assertTrue(all(item["seal_valid"] for item in job["evidence"]))
        self.assertEqual(len(self.ledger.export_receipts(job_id)), 1)
        self.assertTrue(self.ledger.verify_event_chain())
        lkg = self.ledger.last_known_good("farmer-runtime")
        self.assertTrue(lkg["artifact_ref"].startswith("canary:"))

    def test_missing_required_evidence_cannot_complete(self):
        job_id = self.submit_one(executor="static", expected="required_proof")
        supervisor = Supervisor(
            self.ledger,
            self.registry("static", StaticExecutor(success("wrong_proof"))),
            owner="test-supervisor",
        )
        supervisor.tick()
        job = self.ledger.get_job(job_id)
        self.assertEqual(job["state"], JobState.FAILED_FINAL.value)
        self.assertEqual(job["branches"][0]["failure_class"], "evidence_gate")

    def test_evidence_file_waits_for_semantic_state_then_succeeds(self):
        receipt = self.root / "adaptive-driver-result.json"
        receipt.write_text(
            json.dumps({"state": "waiting", "system_driver_changed": False}),
            encoding="utf-8",
        )
        job_id = self.ledger.submit(
            JobSpec(
                goal="wait for verified physical adaptive-driver evidence",
                branches=(
                    BranchSpec(
                        id="physical-result",
                        label="verified physical result",
                        executor="evidence_file",
                        payload={
                            "path": str(receipt),
                            "required_json": {
                                "state": "completed",
                                "decision": ["promoted", "eligible-held"],
                                "system_driver_changed": False,
                            },
                            "required_json_present": ["lkg.rollback.snapshot"],
                            "poll_seconds": 0.01,
                            "evidence_kind": "adaptive_driver_physical_result",
                        },
                        expected_evidence=(
                            EvidenceRequirement("adaptive_driver_physical_result"),
                        ),
                        max_attempts=3,
                    ),
                ),
            )
        )[0]
        registry = self.registry("evidence_file", EvidenceFileExecutor())
        supervisor = Supervisor(self.ledger, registry, owner="semantic-evidence")
        first = supervisor.tick()
        self.assertEqual(first["job_state"], JobState.WAITING.value)
        receipt.write_text(
            json.dumps(
                {
                    "state": "completed",
                    "decision": "promoted",
                    "system_driver_changed": False,
                    "lkg": {"rollback": {"snapshot": "lkg-snapshots/reference.json"}},
                }
            ),
            encoding="utf-8",
        )
        self.ledger.resume(
            job_id,
            changed_dimension="evidence",
            note="adaptive-driver receipt reached its semantic success state",
        )
        second = supervisor.tick()
        self.assertEqual(second["job_state"], JobState.SUCCEEDED.value)
        job = self.ledger.get_job(job_id)
        self.assertEqual(job["state"], JobState.SUCCEEDED.value)
        self.assertTrue(
            any(item["kind"] == "adaptive_driver_physical_result" for item in job["evidence"])
        )

    def test_future_branch_scheduler_executes_safe_branch_before_human_edge(self):
        job_id = self.ledger.submit(
            JobSpec(
                goal="advance the safe prefix",
                branches=(
                    BranchSpec(
                        id="physical",
                        label="high-confidence physical edge",
                        executor="noop",
                        priority=100,
                        confidence=1.0,
                        human_boundary=HumanBoundary(
                            kind="physical_action",
                            summary="insert device",
                            requested_action="insert the device",
                        ),
                    ),
                    BranchSpec(
                        id="safe",
                        label="safe reversible preparation",
                        executor="noop",
                        expected_evidence=(EvidenceRequirement("noop_verified"),),
                        priority=80,
                        confidence=0.8,
                    ),
                ),
            )
        )[0]
        Supervisor(self.ledger, self.registry(), owner="scheduler").tick()
        job = self.ledger.get_job(job_id)
        self.assertEqual(job["state"], JobState.SUCCEEDED.value)
        running_branch = next(item for item in job["branches"] if item["logical_id"] == "safe")
        self.assertEqual(running_branch["state"], "SUCCEEDED")

    def test_watchdog_recovers_expired_attempt_across_ledger_reopen(self):
        job_id = self.submit_one(max_attempts=2)
        first = self.ledger.claim_next("dead-runner", lease_seconds=0)
        self.assertIsNotNone(first)
        reopened = Ledger(self.db, signing_key_path=self.key)
        recovered = reopened.recover_stale_attempts()
        self.assertEqual(recovered, [job_id])
        state = reopened.get_job(job_id)
        self.assertEqual(state["state"], JobState.RECOVERING.value)
        Supervisor(reopened, self.registry(), owner="replacement-runner").tick()
        self.assertEqual(reopened.get_job(job_id)["state"], JobState.SUCCEEDED.value)
        self.assertEqual(reopened.get_job(job_id)["attempts"][0]["state"], "ABANDONED")

    def test_transient_retry_requires_explicit_changed_state_to_resume_immediately(self):
        failure = ExecutionResult(
            outcome=Outcome.FAILED,
            summary="dependency unavailable",
            failure_class="dependency_unavailable",
            retryable=True,
            failure_fingerprint="dependency-v1",
        )
        job_id = self.submit_one(executor="flaky", expected="verified_result", max_attempts=2)
        executor = StaticExecutor(failure, success())
        supervisor = Supervisor(self.ledger, self.registry("flaky", executor), owner="retry-runner")
        supervisor.tick()
        self.assertEqual(self.ledger.get_job(job_id)["state"], JobState.RETRYING.value)
        self.ledger.resume(job_id, changed_dimension="dependency", note="dependency is now available")
        supervisor.tick()
        self.assertEqual(self.ledger.get_job(job_id)["state"], JobState.SUCCEEDED.value)

    def test_human_boundary_is_durable_and_resumes_after_authority_change(self):
        boundary = HumanBoundary(
            kind="credential",
            summary="credential must be entered by its owner",
            requested_action="sign in, then resume",
        )
        executor = StaticExecutor(
            ExecutionResult(outcome=Outcome.HUMAN_REQUIRED, summary=boundary.summary, human_boundary=boundary),
            success(),
        )
        job_id = self.submit_one(executor="boundary", expected="verified_result", max_attempts=2)
        supervisor = Supervisor(self.ledger, self.registry("boundary", executor), owner="boundary-runner")
        supervisor.tick()
        blocked = self.ledger.get_job(job_id)
        self.assertEqual(blocked["state"], JobState.BLOCKED_HUMAN.value)
        self.assertEqual(blocked["human_boundary"]["kind"], "credential")
        reopened = Ledger(self.db, signing_key_path=self.key)
        reopened.resume(job_id, changed_dimension="authority", note="owner completed sign-in")
        Supervisor(reopened, self.registry("boundary", executor), owner="boundary-runner").tick()
        self.assertEqual(reopened.get_job(job_id)["state"], JobState.SUCCEEDED.value)

    def test_dedupe_key_prevents_equivalent_replay(self):
        spec = JobSpec(
            goal="same semantic task",
            dedupe_key="semantic-state-v1",
            branches=(BranchSpec(id="one", label="one", executor="noop"),),
        )
        first = self.ledger.submit(spec)
        second = self.ledger.submit(spec)
        self.assertEqual(first[0], second[0])
        self.assertTrue(first[1])
        self.assertFalse(second[1])

    def test_failed_speculation_never_replaces_last_known_good(self):
        first_id = self.submit_one(executor="good", expected="verified_result", lkg_scope="seed")
        Supervisor(
            self.ledger,
            self.registry("good", StaticExecutor(success(lkg_ref="artifact:good"))),
            owner="lkg-good",
        ).tick()
        original = self.ledger.last_known_good("seed")
        self.assertEqual(original["job_id"], first_id)
        second_id = self.submit_one(executor="bad", expected="verified_result", lkg_scope="seed")
        failure = ExecutionResult(
            outcome=Outcome.FAILED,
            summary="candidate failed",
            failure_class="verification",
            failure_fingerprint="bad-v1",
        )
        Supervisor(self.ledger, self.registry("bad", StaticExecutor(failure)), owner="lkg-good").tick()
        self.assertEqual(self.ledger.get_job(second_id)["state"], JobState.FAILED_FINAL.value)
        self.assertEqual(self.ledger.last_known_good("seed"), original)

    def test_chat_to_git_adapter_returns_run_feedback_and_artifact_evidence(self):
        executor = FakeChatToGitExecutor()
        result = executor.execute(
            {
                "id": "ATT-1",
                "job_id": "AF-123",
                "goal": "repository status",
                "payload": {
                    "prompt": "check repository status",
                    "task": {"type": "repository_status", "parameters": {}},
                    "observe_seconds": 5,
                },
            }
        )
        self.assertEqual(result.outcome, Outcome.SUCCEEDED)
        self.assertEqual(executor.dispatched, 1)
        self.assertEqual(
            {item.kind for item in result.evidence},
            {"chat_to_git_dispatch", "github_issue_feedback", "github_actions_run", "chat_to_git_receipt"},
        )

    def test_evidence_and_event_tables_are_append_only(self):
        job_id = self.submit_one()
        Supervisor(self.ledger, self.registry(), owner="immutable").tick()
        with closing(self.ledger._connect()) as connection:
            evidence_id = connection.execute(
                "SELECT id FROM evidence WHERE job_id=? LIMIT 1", (job_id,)
            ).fetchone()["id"]
            with self.assertRaises(Exception):
                connection.execute("UPDATE evidence SET source='tampered' WHERE id=?", (evidence_id,))
            with self.assertRaises(Exception):
                connection.execute("DELETE FROM events WHERE sequence=1")


if __name__ == "__main__":
    unittest.main()
