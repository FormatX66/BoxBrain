"""Durable SQLite execution ledger with tamper-evident evidence and receipts."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import uuid
from dataclasses import asdict
from contextlib import closing
from pathlib import Path
from typing import Any, Iterable, Mapping

from .models import (
    BranchSpec,
    BranchState,
    ExecutionResult,
    HumanBoundary,
    JobSpec,
    JobState,
    Outcome,
    TERMINAL_STATES,
    transition_allowed,
)


SCHEMA_VERSION = 1


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _json(value: Any) -> str:
    return canonical_json(value)


def _loads(value: str | None, default: Any = None) -> Any:
    return default if value is None else json.loads(value)


def _now() -> float:
    return time.time()


class LedgerError(RuntimeError):
    """Base ledger error."""


class StateTransitionError(LedgerError):
    """Raised when a caller attempts an illegal job transition."""


class Ledger:
    """Authoritative Farmer state, evidence, attempt, and recovery ledger."""

    def __init__(self, path: str | os.PathLike[str], *, signing_key_path: str | os.PathLike[str] | None = None):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.signing_key_path = Path(signing_key_path).expanduser().resolve() if signing_key_path else self.path.with_suffix(".key")
        self._signing_key = self._load_or_create_signing_key()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _load_or_create_signing_key(self) -> bytes:
        self.signing_key_path.parent.mkdir(parents=True, exist_ok=True)
        if self.signing_key_path.exists():
            raw = self.signing_key_path.read_bytes()
            if len(raw) < 32:
                raise LedgerError("Farmer signing key is invalid")
            return raw
        raw = secrets.token_bytes(32)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor = os.open(self.signing_key_path, flags, 0o600)
        try:
            os.write(descriptor, raw)
        finally:
            os.close(descriptor)
        try:
            os.chmod(self.signing_key_path, 0o600)
        except OSError:
            pass
        return raw

    def _initialize(self) -> None:
        schema = """
        PRAGMA journal_mode = WAL;
        PRAGMA synchronous = FULL;
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            goal TEXT NOT NULL,
            state TEXT NOT NULL,
            priority INTEGER NOT NULL,
            dedupe_key TEXT UNIQUE,
            context_json TEXT NOT NULL,
            current_branch_id TEXT,
            next_action TEXT,
            human_boundary_json TEXT,
            lease_owner TEXT,
            lease_expires_at REAL,
            retry_not_before REAL,
            lkg_ref TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            completed_at REAL,
            version INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS branches (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id),
            logical_id TEXT NOT NULL,
            label TEXT NOT NULL,
            executor TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            expected_evidence_json TEXT NOT NULL,
            state TEXT NOT NULL,
            priority INTEGER NOT NULL,
            confidence REAL NOT NULL,
            impact REAL NOT NULL,
            evidence_quality REAL NOT NULL,
            risk REAL NOT NULL,
            cost REAL NOT NULL,
            reversibility REAL NOT NULL,
            authority_ready INTEGER NOT NULL,
            dependencies_satisfied INTEGER NOT NULL,
            human_boundary_json TEXT,
            max_attempts INTEGER NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            eligible_after REAL,
            failure_class TEXT,
            failure_fingerprint TEXT,
            lkg_scope TEXT,
            next_action TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(job_id, logical_id)
        );
        CREATE TABLE IF NOT EXISTS attempts (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id),
            branch_id TEXT NOT NULL REFERENCES branches(id),
            attempt_number INTEGER NOT NULL,
            executor TEXT NOT NULL,
            owner TEXT NOT NULL,
            state TEXT NOT NULL,
            started_at REAL NOT NULL,
            heartbeat_at REAL NOT NULL,
            ended_at REAL,
            outcome TEXT,
            summary TEXT,
            failure_class TEXT,
            failure_fingerprint TEXT,
            receipt_evidence_id TEXT,
            UNIQUE(branch_id, attempt_number)
        );
        CREATE TABLE IF NOT EXISTS evidence (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id),
            branch_id TEXT REFERENCES branches(id),
            attempt_id TEXT REFERENCES attempts(id),
            kind TEXT NOT NULL,
            source TEXT NOT NULL,
            verified INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            payload_sha256 TEXT NOT NULL,
            signature TEXT NOT NULL,
            created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at REAL NOT NULL,
            previous_hash TEXT NOT NULL,
            event_hash TEXT NOT NULL,
            signature TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS last_known_good (
            scope TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id),
            branch_id TEXT NOT NULL REFERENCES branches(id),
            receipt_evidence_id TEXT NOT NULL REFERENCES evidence(id),
            artifact_ref TEXT NOT NULL,
            manifest_json TEXT NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS supervisor_leases (
            name TEXT PRIMARY KEY,
            owner TEXT NOT NULL,
            heartbeat_at REAL NOT NULL,
            expires_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS jobs_schedulable ON jobs(state, retry_not_before, priority);
        CREATE INDEX IF NOT EXISTS branches_schedulable ON branches(job_id, state, eligible_after);
        CREATE INDEX IF NOT EXISTS attempts_active ON attempts(state, heartbeat_at);
        CREATE INDEX IF NOT EXISTS evidence_job ON evidence(job_id, kind);
        CREATE TRIGGER IF NOT EXISTS evidence_immutable_update
            BEFORE UPDATE ON evidence BEGIN SELECT RAISE(ABORT, 'evidence is append-only'); END;
        CREATE TRIGGER IF NOT EXISTS evidence_immutable_delete
            BEFORE DELETE ON evidence BEGIN SELECT RAISE(ABORT, 'evidence is append-only'); END;
        CREATE TRIGGER IF NOT EXISTS events_immutable_update
            BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
        CREATE TRIGGER IF NOT EXISTS events_immutable_delete
            BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
        """
        with closing(self._connect()) as connection:
            connection.executescript(schema)
            current = connection.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
            if current is None:
                connection.execute(
                    "INSERT INTO metadata(key, value) VALUES('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
            elif int(current["value"]) != SCHEMA_VERSION:
                raise LedgerError(f"unsupported ledger schema version: {current['value']}")

    def _sign(self, digest: str) -> str:
        return hmac.new(self._signing_key, digest.encode("ascii"), hashlib.sha256).hexdigest()

    def _seal_payload(self, payload: Mapping[str, Any]) -> tuple[str, str, str]:
        payload_json = canonical_json(payload)
        digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        return payload_json, digest, self._sign(digest)

    def _append_event(
        self,
        connection: sqlite3.Connection,
        entity_type: str,
        entity_id: str,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> None:
        previous = connection.execute(
            "SELECT event_hash FROM events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous_hash = previous["event_hash"] if previous else "GENESIS"
        created_at = _now()
        payload_json = canonical_json(payload)
        event_body = canonical_json(
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "event_type": event_type,
                "payload": payload,
                "created_at": created_at,
                "previous_hash": previous_hash,
            }
        )
        event_hash = hashlib.sha256(event_body.encode("utf-8")).hexdigest()
        connection.execute(
            """INSERT INTO events(
                entity_type, entity_id, event_type, payload_json, created_at,
                previous_hash, event_hash, signature
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entity_type,
                entity_id,
                event_type,
                payload_json,
                created_at,
                previous_hash,
                event_hash,
                self._sign(event_hash),
            ),
        )

    def _transition(
        self,
        connection: sqlite3.Connection,
        job_id: str,
        target: JobState,
        *,
        reason: str,
        fields: Mapping[str, Any] | None = None,
    ) -> None:
        row = connection.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise LedgerError(f"job not found: {job_id}")
        current = JobState(row["state"])
        if current == target:
            return
        if not transition_allowed(current, target):
            raise StateTransitionError(f"illegal Farmer transition {current.value} -> {target.value}")
        values = dict(fields or {})
        values["state"] = target.value
        values["updated_at"] = _now()
        assignments = []
        parameters: list[Any] = []
        for key, value in values.items():
            if key == "version":
                continue
            assignments.append(f"{key}=?")
            parameters.append(value)
        assignments.append("version=version+1")
        parameters.append(job_id)
        connection.execute(f"UPDATE jobs SET {', '.join(assignments)} WHERE id=?", parameters)
        self._append_event(
            connection,
            "job",
            job_id,
            "state_transition",
            {"from": current.value, "to": target.value, "reason": reason},
        )

    def submit(self, spec: JobSpec) -> tuple[str, bool]:
        """Persist a job and its complete Future Branch field atomically.

        Returns ``(job_id, created)``. A matching dedupe key returns the existing
        durable job instead of replaying equivalent work.
        """
        spec.validate()
        now = _now()
        job_id = spec.id or f"AF-{uuid.uuid4().hex[:20]}"
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            if spec.dedupe_key:
                existing = connection.execute(
                    "SELECT id FROM jobs WHERE dedupe_key=?", (spec.dedupe_key,)
                ).fetchone()
                if existing:
                    connection.commit()
                    return existing["id"], False
            connection.execute(
                """INSERT INTO jobs(
                    id, goal, state, priority, dedupe_key, context_json,
                    created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job_id,
                    spec.goal,
                    JobState.RECEIVED.value,
                    spec.priority,
                    spec.dedupe_key,
                    _json(spec.context),
                    now,
                    now,
                ),
            )
            self._append_event(
                connection,
                "job",
                job_id,
                "received",
                {"goal": spec.goal, "priority": spec.priority, "dedupe_key": spec.dedupe_key},
            )
            for branch in spec.branches:
                branch_id = f"{job_id}:{branch.id}"
                connection.execute(
                    """INSERT INTO branches(
                        id, job_id, logical_id, label, executor, payload_json,
                        expected_evidence_json, state, priority, confidence, impact,
                        evidence_quality, risk, cost, reversibility, authority_ready,
                        dependencies_satisfied, human_boundary_json, max_attempts,
                        lkg_scope, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        branch_id,
                        job_id,
                        branch.id,
                        branch.label,
                        branch.executor,
                        _json(branch.payload),
                        _json([asdict(item) for item in branch.expected_evidence]),
                        BranchState.CANDIDATE.value,
                        branch.priority,
                        branch.confidence,
                        branch.impact,
                        branch.evidence_quality,
                        branch.risk,
                        branch.cost,
                        branch.reversibility,
                        int(branch.authority_ready),
                        int(branch.dependencies_satisfied),
                        _json(asdict(branch.human_boundary)) if branch.human_boundary else None,
                        branch.max_attempts,
                        branch.lkg_scope,
                        now,
                        now,
                    ),
                )
                self._append_event(
                    connection,
                    "branch",
                    branch_id,
                    "candidate_recorded",
                    {"executor": branch.executor, "label": branch.label},
                )
            self._transition(connection, job_id, JobState.PLANNED, reason="Future Branch field persisted")
            self._transition(connection, job_id, JobState.READY, reason="eligible for supervisor scheduling")
            connection.commit()
            return job_id, True
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def branch_score(branch: Mapping[str, Any]) -> float:
        """Rank branches using Future Branch value, evidence, safety, and authority."""
        if not branch["authority_ready"] or not branch["dependencies_satisfied"]:
            return float("-inf")
        if branch.get("human_boundary_json"):
            return float("-inf")
        utility = (
            0.24 * float(branch["confidence"])
            + 0.18 * float(branch["impact"])
            + 0.18 * float(branch["evidence_quality"])
            + 0.14 * float(branch["reversibility"])
            + 0.16 * (float(branch["priority"]) / 100.0)
            + 0.10
        )
        penalty = 0.30 * float(branch["risk"]) + 0.10 * min(float(branch["cost"]), 1.0)
        return utility - penalty

    def _activate_due(self, connection: sqlite3.Connection, now: float) -> None:
        rows = connection.execute(
            """SELECT id, state FROM jobs
               WHERE state IN (?, ?, ?) AND COALESCE(retry_not_before, 0) <= ?
                 AND human_boundary_json IS NULL""",
            (JobState.RETRYING.value, JobState.RECOVERING.value, JobState.WAITING.value, now),
        ).fetchall()
        for row in rows:
            self._transition(connection, row["id"], JobState.READY, reason="retry/recovery prerequisite became eligible")

    def claim_next(self, owner: str, *, lease_seconds: float = 90.0) -> dict[str, Any] | None:
        """Atomically select the best eligible branch from the highest-priority job."""
        now = _now()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._activate_due(connection, now)
            jobs = connection.execute(
                "SELECT * FROM jobs WHERE state=? ORDER BY priority DESC, created_at ASC",
                (JobState.READY.value,),
            ).fetchall()
            for job in jobs:
                candidates = connection.execute(
                    """SELECT * FROM branches
                       WHERE job_id=? AND state IN (?, ?, ?)
                         AND attempt_count < max_attempts
                         AND COALESCE(eligible_after, 0) <= ?""",
                    (
                        job["id"],
                        BranchState.CANDIDATE.value,
                        BranchState.RETRYABLE.value,
                        BranchState.WAITING.value,
                        now,
                    ),
                ).fetchall()
                eligible = [
                    dict(item)
                    for item in candidates
                    if item["authority_ready"]
                    and item["dependencies_satisfied"]
                    and item["human_boundary_json"] is None
                ]
                if not eligible:
                    boundary = next((item for item in candidates if item["human_boundary_json"]), None)
                    if boundary:
                        self._transition(
                            connection,
                            job["id"],
                            JobState.BLOCKED_HUMAN,
                            reason="only a real human boundary remains",
                            fields={
                                "human_boundary_json": boundary["human_boundary_json"],
                                "next_action": _loads(boundary["human_boundary_json"])["requested_action"],
                            },
                        )
                    else:
                        self._transition(
                            connection,
                            job["id"],
                            JobState.WAITING,
                            reason="no dependency- and authority-ready branch",
                            fields={"retry_not_before": now + 30.0},
                        )
                    continue
                selected = max(
                    eligible,
                    key=lambda item: (self.branch_score(item), item["priority"], item["logical_id"]),
                )
                branch_id = selected["id"]
                attempt_number = int(selected["attempt_count"]) + 1
                attempt_id = f"ATT-{uuid.uuid4().hex}"
                connection.execute(
                    """UPDATE branches SET state=?, attempt_count=?, updated_at=? WHERE id=?""",
                    (BranchState.RUNNING.value, attempt_number, now, branch_id),
                )
                connection.execute(
                    """INSERT INTO attempts(
                        id, job_id, branch_id, attempt_number, executor, owner,
                        state, started_at, heartbeat_at
                    ) VALUES(?, ?, ?, ?, ?, ?, 'RUNNING', ?, ?)""",
                    (
                        attempt_id,
                        job["id"],
                        branch_id,
                        attempt_number,
                        selected["executor"],
                        owner,
                        now,
                        now,
                    ),
                )
                self._transition(
                    connection,
                    job["id"],
                    JobState.RUNNING,
                    reason=f"Future Branch {selected['logical_id']} selected",
                    fields={
                        "current_branch_id": branch_id,
                        "lease_owner": owner,
                        "lease_expires_at": now + lease_seconds,
                        "next_action": f"execute {selected['executor']}",
                    },
                )
                self._append_event(
                    connection,
                    "attempt",
                    attempt_id,
                    "started",
                    {
                        "job_id": job["id"],
                        "branch_id": branch_id,
                        "attempt_number": attempt_number,
                        "owner": owner,
                        "score": self.branch_score(selected),
                    },
                )
                connection.commit()
                return self.attempt_context(attempt_id)
            connection.commit()
            return None
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def heartbeat_attempt(self, attempt_id: str, owner: str, *, lease_seconds: float = 90.0) -> bool:
        now = _now()
        with closing(self._connect()) as connection:
            attempt = connection.execute(
                "SELECT job_id, owner, state FROM attempts WHERE id=?", (attempt_id,)
            ).fetchone()
            if attempt is None or attempt["owner"] != owner or attempt["state"] != "RUNNING":
                return False
            connection.execute("UPDATE attempts SET heartbeat_at=? WHERE id=?", (now, attempt_id))
            connection.execute(
                "UPDATE jobs SET lease_expires_at=?, updated_at=? WHERE id=? AND lease_owner=?",
                (now + lease_seconds, now, attempt["job_id"], owner),
            )
            return True

    def _record_evidence(
        self,
        connection: sqlite3.Connection,
        *,
        job_id: str,
        branch_id: str,
        attempt_id: str,
        kind: str,
        source: str,
        verified: bool,
        payload: Mapping[str, Any],
    ) -> str:
        evidence_id = f"EVD-{uuid.uuid4().hex}"
        payload_json, digest, signature = self._seal_payload(payload)
        connection.execute(
            """INSERT INTO evidence(
                id, job_id, branch_id, attempt_id, kind, source, verified,
                payload_json, payload_sha256, signature, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                evidence_id,
                job_id,
                branch_id,
                attempt_id,
                kind,
                source,
                int(verified),
                payload_json,
                digest,
                signature,
                _now(),
            ),
        )
        return evidence_id

    def _evidence_valid(self, row: Mapping[str, Any]) -> bool:
        digest = hashlib.sha256(row["payload_json"].encode("utf-8")).hexdigest()
        return (
            hmac.compare_digest(digest, row["payload_sha256"])
            and hmac.compare_digest(self._sign(digest), row["signature"])
        )

    def _requirements_satisfied(
        self,
        connection: sqlite3.Connection,
        branch: Mapping[str, Any],
        attempt_id: str,
    ) -> tuple[bool, str]:
        rows = connection.execute(
            "SELECT * FROM evidence WHERE attempt_id=?", (attempt_id,)
        ).fetchall()
        if not rows:
            return False, "no evidence was recorded"
        for row in rows:
            if not self._evidence_valid(row):
                return False, f"evidence seal failed: {row['id']}"
        requirements = _loads(branch["expected_evidence_json"], [])
        for requirement in requirements:
            count = sum(
                1
                for row in rows
                if row["kind"] == requirement["kind"] and bool(row["verified"])
            )
            if count < int(requirement.get("minimum", 1)):
                return False, f"missing verified evidence kind: {requirement['kind']}"
        receipts = [row for row in rows if row["kind"] == "farmer_receipt" and row["verified"]]
        if len(receipts) != 1:
            return False, "exactly one signed Farmer receipt is required"
        return True, "signed receipt and required evidence verified"

    def _close_attempt(
        self,
        connection: sqlite3.Connection,
        attempt_id: str,
        result: ExecutionResult,
        receipt_evidence_id: str,
        state: str,
    ) -> None:
        connection.execute(
            """UPDATE attempts SET state=?, ended_at=?, outcome=?, summary=?,
               failure_class=?, failure_fingerprint=?, receipt_evidence_id=? WHERE id=?""",
            (
                state,
                _now(),
                result.outcome.value,
                result.summary,
                result.failure_class,
                result.failure_fingerprint,
                receipt_evidence_id,
                attempt_id,
            ),
        )

    def _clear_lease_fields(self) -> dict[str, Any]:
        return {
            "lease_owner": None,
            "lease_expires_at": None,
            "current_branch_id": None,
        }

    def finish_attempt(self, attempt_id: str, owner: str, result: ExecutionResult) -> dict[str, Any]:
        """Persist an executor result, seal its receipt, verify, and transition."""
        result.validate()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            attempt = connection.execute("SELECT * FROM attempts WHERE id=?", (attempt_id,)).fetchone()
            if attempt is None:
                raise LedgerError(f"attempt not found: {attempt_id}")
            if attempt["owner"] != owner or attempt["state"] != "RUNNING":
                raise LedgerError("attempt lease is not owned by this supervisor")
            job = connection.execute("SELECT * FROM jobs WHERE id=?", (attempt["job_id"],)).fetchone()
            branch = connection.execute("SELECT * FROM branches WHERE id=?", (attempt["branch_id"],)).fetchone()
            if job["state"] != JobState.RUNNING.value:
                raise StateTransitionError(f"job is not RUNNING: {job['state']}")

            evidence_ids: list[str] = []
            for item in result.evidence:
                evidence_ids.append(
                    self._record_evidence(
                        connection,
                        job_id=job["id"],
                        branch_id=branch["id"],
                        attempt_id=attempt_id,
                        kind=item.kind,
                        source=item.source,
                        verified=item.verified,
                        payload=dict(item.data),
                    )
                )
            receipt = {
                "schema": "aurum.farmer.receipt.v1",
                "job_id": job["id"],
                "goal": job["goal"],
                "branch_id": branch["logical_id"],
                "executor": branch["executor"],
                "attempt_id": attempt_id,
                "attempt_number": attempt["attempt_number"],
                "owner": owner,
                "outcome": result.outcome.value,
                "summary": result.summary,
                "evidence_ids": evidence_ids,
                "failure_class": result.failure_class,
                "failure_fingerprint": result.failure_fingerprint,
                "changed_dimensions": sorted(result.changed_dimensions),
                "started_at": attempt["started_at"],
                "finished_at": _now(),
            }
            receipt_id = self._record_evidence(
                connection,
                job_id=job["id"],
                branch_id=branch["id"],
                attempt_id=attempt_id,
                kind="farmer_receipt",
                source="aurum-farmer",
                verified=True,
                payload=receipt,
            )

            if result.outcome in {Outcome.SUCCEEDED, Outcome.NO_CHANGE}:
                self._transition(connection, job["id"], JobState.VERIFYING, reason="executor returned a candidate result")
                valid, verification_summary = self._requirements_satisfied(connection, branch, attempt_id)
                if valid:
                    connection.execute(
                        "UPDATE branches SET state=?, updated_at=?, next_action=NULL WHERE id=?",
                        (BranchState.SUCCEEDED.value, _now(), branch["id"]),
                    )
                    completion_fields = self._clear_lease_fields()
                    completion_fields.update(
                        {
                            "completed_at": _now(),
                            "next_action": None,
                            "human_boundary_json": None,
                            "lkg_ref": result.lkg_ref or job["lkg_ref"],
                        }
                    )
                    self._transition(
                        connection,
                        job["id"],
                        JobState.SUCCEEDED,
                        reason=verification_summary,
                        fields=completion_fields,
                    )
                    self._close_attempt(connection, attempt_id, result, receipt_id, "VERIFIED")
                    if branch["lkg_scope"] and result.lkg_ref:
                        connection.execute(
                            """INSERT INTO last_known_good(
                                scope, job_id, branch_id, receipt_evidence_id,
                                artifact_ref, manifest_json, updated_at
                            ) VALUES(?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(scope) DO UPDATE SET
                                job_id=excluded.job_id,
                                branch_id=excluded.branch_id,
                                receipt_evidence_id=excluded.receipt_evidence_id,
                                artifact_ref=excluded.artifact_ref,
                                manifest_json=excluded.manifest_json,
                                updated_at=excluded.updated_at""",
                            (
                                branch["lkg_scope"],
                                job["id"],
                                branch["id"],
                                receipt_id,
                                result.lkg_ref,
                                _json({"receipt": receipt_id, "evidence": evidence_ids}),
                                _now(),
                            ),
                        )
                        self._append_event(
                            connection,
                            "lkg",
                            branch["lkg_scope"],
                            "promoted",
                            {"job_id": job["id"], "artifact_ref": result.lkg_ref, "receipt": receipt_id},
                        )
                else:
                    evidence_failure = ExecutionResult(
                        outcome=Outcome.FAILED,
                        summary=verification_summary,
                        failure_class="evidence_gate",
                        failure_fingerprint=f"evidence-gate:{verification_summary}",
                    )
                    self._schedule_or_fail(connection, job, branch, evidence_failure, from_state=JobState.VERIFYING)
                    self._close_attempt(connection, attempt_id, evidence_failure, receipt_id, "REJECTED")
            elif result.outcome == Outcome.HUMAN_REQUIRED:
                boundary_json = _json(asdict(result.human_boundary))
                connection.execute(
                    "UPDATE branches SET state=?, human_boundary_json=?, next_action=?, updated_at=? WHERE id=?",
                    (
                        BranchState.BLOCKED_HUMAN.value,
                        boundary_json,
                        result.human_boundary.requested_action,
                        _now(),
                        branch["id"],
                    ),
                )
                fields = self._clear_lease_fields()
                fields.update(
                    {
                        "human_boundary_json": boundary_json,
                        "next_action": result.human_boundary.requested_action,
                    }
                )
                self._transition(
                    connection,
                    job["id"],
                    JobState.BLOCKED_HUMAN,
                    reason=result.human_boundary.summary,
                    fields=fields,
                )
                self._close_attempt(connection, attempt_id, result, receipt_id, "BLOCKED_HUMAN")
            elif result.outcome == Outcome.WAITING:
                delay = max(result.retry_after_seconds, 5.0)
                connection.execute(
                    "UPDATE branches SET state=?, eligible_after=?, next_action=?, updated_at=? WHERE id=?",
                    (BranchState.WAITING.value, _now() + delay, result.next_action, _now(), branch["id"]),
                )
                fields = self._clear_lease_fields()
                fields.update({"retry_not_before": _now() + delay, "next_action": result.next_action})
                self._transition(connection, job["id"], JobState.WAITING, reason=result.summary, fields=fields)
                self._close_attempt(connection, attempt_id, result, receipt_id, "WAITING")
            else:
                self._schedule_or_fail(connection, job, branch, result, from_state=JobState.RUNNING)
                self._close_attempt(connection, attempt_id, result, receipt_id, "FAILED")

            self._append_event(
                connection,
                "attempt",
                attempt_id,
                "finished",
                {"outcome": result.outcome.value, "receipt": receipt_id, "summary": result.summary},
            )
            connection.commit()
            return self.get_job(job["id"])
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _schedule_or_fail(
        self,
        connection: sqlite3.Connection,
        job: Mapping[str, Any],
        branch: Mapping[str, Any],
        result: ExecutionResult,
        *,
        from_state: JobState,
    ) -> None:
        attempts_remaining = int(branch["attempt_count"]) < int(branch["max_attempts"])
        same_stable_failure = (
            bool(result.failure_fingerprint)
            and result.failure_fingerprint == branch["failure_fingerprint"]
            and (result.failure_class or "") not in {"rate_limit", "transport", "dependency_unavailable", "runner_lost", "timeout"}
        )
        if result.permits_retry and attempts_remaining and not same_stable_failure:
            delay = max(result.retry_after_seconds, min(300.0, 2.0 ** int(branch["attempt_count"])))
            connection.execute(
                """UPDATE branches SET state=?, eligible_after=?, failure_class=?,
                   failure_fingerprint=?, next_action=?, updated_at=? WHERE id=?""",
                (
                    BranchState.RETRYABLE.value,
                    _now() + delay,
                    result.failure_class,
                    result.failure_fingerprint,
                    result.next_action or f"retry after {delay:.0f}s",
                    _now(),
                    branch["id"],
                ),
            )
            fields = self._clear_lease_fields()
            fields.update(
                {
                    "retry_not_before": _now() + delay,
                    "next_action": result.next_action or f"retry after {delay:.0f}s",
                }
            )
            self._transition(
                connection,
                job["id"],
                JobState.RETRYING,
                reason=f"{result.failure_class or 'failure'} classified retryable",
                fields=fields,
            )
            return
        connection.execute(
            """UPDATE branches SET state=?, failure_class=?, failure_fingerprint=?,
               next_action=?, updated_at=? WHERE id=?""",
            (
                BranchState.QUARANTINED.value,
                result.failure_class,
                result.failure_fingerprint,
                result.next_action,
                _now(),
                branch["id"],
            ),
        )
        alternates = connection.execute(
            """SELECT COUNT(*) AS count FROM branches WHERE job_id=? AND id<>?
               AND state IN (?, ?, ?) AND attempt_count < max_attempts""",
            (
                job["id"],
                branch["id"],
                BranchState.CANDIDATE.value,
                BranchState.RETRYABLE.value,
                BranchState.WAITING.value,
            ),
        ).fetchone()["count"]
        fields = self._clear_lease_fields()
        if alternates:
            fields.update({"retry_not_before": _now(), "next_action": "promote the next warm Future Branch"})
            self._transition(
                connection,
                job["id"],
                JobState.RECOVERING,
                reason=f"failed branch quarantined: {result.summary}",
                fields=fields,
            )
        else:
            fields.update({"completed_at": _now(), "next_action": result.next_action or result.summary})
            self._transition(
                connection,
                job["id"],
                JobState.FAILED_FINAL,
                reason=f"no eligible recovery branch: {result.summary}",
                fields=fields,
            )

    def recover_stale_attempts(self, *, now: float | None = None) -> list[str]:
        """Move lost runner leases into structural recovery without replaying LKG."""
        current = _now() if now is None else now
        recovered: list[str] = []
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            jobs = connection.execute(
                """SELECT * FROM jobs WHERE state IN (?, ?) AND lease_expires_at IS NOT NULL
                   AND lease_expires_at < ?""",
                (JobState.RUNNING.value, JobState.VERIFYING.value, current),
            ).fetchall()
            for job in jobs:
                attempt = connection.execute(
                    """SELECT * FROM attempts WHERE job_id=? AND state='RUNNING'
                       ORDER BY started_at DESC LIMIT 1""",
                    (job["id"],),
                ).fetchone()
                branch = connection.execute("SELECT * FROM branches WHERE id=?", (job["current_branch_id"],)).fetchone()
                if attempt:
                    connection.execute(
                        """UPDATE attempts SET state='ABANDONED', ended_at=?, outcome='failed',
                           summary='runner lease expired', failure_class='runner_lost' WHERE id=?""",
                        (current, attempt["id"]),
                    )
                if branch and int(branch["attempt_count"]) < int(branch["max_attempts"]):
                    connection.execute(
                        """UPDATE branches SET state=?, eligible_after=?, failure_class='runner_lost',
                           next_action='resume after lost runner lease', updated_at=? WHERE id=?""",
                        (BranchState.RETRYABLE.value, current, current, branch["id"]),
                    )
                    fields = self._clear_lease_fields()
                    fields.update({"retry_not_before": current, "next_action": "resume after lost runner lease"})
                    self._transition(
                        connection,
                        job["id"],
                        JobState.RECOVERING,
                        reason="watchdog detected an expired runner lease",
                        fields=fields,
                    )
                else:
                    fields = self._clear_lease_fields()
                    fields.update({"completed_at": current, "next_action": "inspect exhausted lost-runner recovery"})
                    self._transition(
                        connection,
                        job["id"],
                        JobState.FAILED_FINAL,
                        reason="runner lease expired and recovery attempts are exhausted",
                        fields=fields,
                    )
                recovered.append(job["id"])
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return recovered

    def resume(self, job_id: str, *, changed_dimension: str, note: str) -> None:
        """Resume a human/wait boundary after a named state dimension changed."""
        from .models import RETRY_CHANGE_DIMENSIONS

        if changed_dimension not in RETRY_CHANGE_DIMENSIONS:
            raise ValueError("resume requires a recognized changed dimension")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            job = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if job is None:
                raise LedgerError(f"job not found: {job_id}")
            state = JobState(job["state"])
            if state not in {JobState.BLOCKED_HUMAN, JobState.WAITING, JobState.RETRYING, JobState.RECOVERING}:
                raise StateTransitionError(f"job cannot resume from {state.value}")
            connection.execute(
                """UPDATE branches SET state=?, human_boundary_json=NULL, eligible_after=?,
                   dependencies_satisfied=1, authority_ready=1, updated_at=?
                   WHERE job_id=? AND state IN (?, ?, ?)""",
                (
                    BranchState.CANDIDATE.value,
                    _now(),
                    _now(),
                    job_id,
                    BranchState.BLOCKED_HUMAN.value,
                    BranchState.WAITING.value,
                    BranchState.RETRYABLE.value,
                ),
            )
            self._transition(
                connection,
                job_id,
                JobState.READY,
                reason=f"{changed_dimension} changed: {note}",
                fields={
                    "human_boundary_json": None,
                    "retry_not_before": None,
                    "next_action": "reevaluate Future Branch field",
                },
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def supervisor_heartbeat(self, name: str, owner: str, *, lease_seconds: float) -> bool:
        now = _now()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute("SELECT * FROM supervisor_leases WHERE name=?", (name,)).fetchone()
            if current and current["owner"] != owner and current["expires_at"] > now:
                connection.rollback()
                return False
            connection.execute(
                """INSERT INTO supervisor_leases(name, owner, heartbeat_at, expires_at)
                   VALUES(?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET owner=excluded.owner,
                   heartbeat_at=excluded.heartbeat_at, expires_at=excluded.expires_at""",
                (name, owner, now, now + lease_seconds),
            )
            connection.commit()
            return True
        finally:
            connection.close()

    def attempt_context(self, attempt_id: str) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """SELECT a.*, j.goal, j.context_json, j.priority AS job_priority,
                          b.logical_id, b.label, b.payload_json,
                          b.expected_evidence_json, b.lkg_scope
                   FROM attempts a
                   JOIN jobs j ON j.id=a.job_id
                   JOIN branches b ON b.id=a.branch_id
                   WHERE a.id=?""",
                (attempt_id,),
            ).fetchone()
            if row is None:
                raise LedgerError(f"attempt not found: {attempt_id}")
            value = dict(row)
            value["payload"] = _loads(value.pop("payload_json"), {})
            value["context"] = _loads(value.pop("context_json"), {})
            value["expected_evidence"] = _loads(value.pop("expected_evidence_json"), [])
            value["prior_evidence"] = [
                {
                    "id": evidence["id"],
                    "kind": evidence["kind"],
                    "source": evidence["source"],
                    "verified": bool(evidence["verified"]),
                    "payload": _loads(evidence["payload_json"], {}),
                    "seal_valid": self._evidence_valid(evidence),
                }
                for evidence in connection.execute(
                    """SELECT e.* FROM evidence e
                       JOIN attempts prior ON prior.id=e.attempt_id
                       WHERE e.job_id=? AND e.branch_id=? AND prior.started_at < ?
                       ORDER BY e.created_at""",
                    (value["job_id"], value["branch_id"], value["started_at"]),
                )
            ]
            return value

    def get_job(self, job_id: str) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            job = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if job is None:
                raise LedgerError(f"job not found: {job_id}")
            value = dict(job)
            value["context"] = _loads(value.pop("context_json"), {})
            value["human_boundary"] = _loads(value.pop("human_boundary_json"), None)
            value["branches"] = []
            for row in connection.execute(
                "SELECT * FROM branches WHERE job_id=? ORDER BY created_at, logical_id", (job_id,)
            ):
                branch = dict(row)
                branch["payload"] = _loads(branch.pop("payload_json"), {})
                branch["expected_evidence"] = _loads(branch.pop("expected_evidence_json"), [])
                branch["human_boundary"] = _loads(branch.pop("human_boundary_json"), None)
                branch["score"] = self.branch_score(branch)
                value["branches"].append(branch)
            value["attempts"] = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM attempts WHERE job_id=? ORDER BY started_at", (job_id,)
                )
            ]
            value["evidence"] = [
                {
                    **dict(row),
                    "payload": _loads(row["payload_json"], {}),
                    "seal_valid": self._evidence_valid(row),
                }
                for row in connection.execute(
                    "SELECT * FROM evidence WHERE job_id=? ORDER BY created_at", (job_id,)
                )
            ]
            for item in value["evidence"]:
                item.pop("payload_json", None)
            return value

    def list_jobs(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            return [
                {
                    **dict(row),
                    "context": _loads(row["context_json"], {}),
                    "human_boundary": _loads(row["human_boundary_json"], None),
                }
                for row in connection.execute(
                    "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
                )
            ]

    def last_known_good(self, scope: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM last_known_good WHERE scope=?", (scope,)).fetchone()
            if row is None:
                return None
            value = dict(row)
            value["manifest"] = _loads(value.pop("manifest_json"), {})
            return value

    def stats(self) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            states = {
                row["state"]: row["count"]
                for row in connection.execute("SELECT state, COUNT(*) AS count FROM jobs GROUP BY state")
            }
            running = connection.execute("SELECT COUNT(*) AS count FROM attempts WHERE state='RUNNING'").fetchone()["count"]
            return {
                "schema_version": SCHEMA_VERSION,
                "ledger": str(self.path),
                "states": states,
                "running_attempts": running,
                "event_chain_valid": self.verify_event_chain(),
            }

    def verify_event_chain(self) -> bool:
        previous = "GENESIS"
        with closing(self._connect()) as connection:
            for row in connection.execute("SELECT * FROM events ORDER BY sequence"):
                if row["previous_hash"] != previous:
                    return False
                body = canonical_json(
                    {
                        "entity_type": row["entity_type"],
                        "entity_id": row["entity_id"],
                        "event_type": row["event_type"],
                        "payload": _loads(row["payload_json"], {}),
                        "created_at": row["created_at"],
                        "previous_hash": row["previous_hash"],
                    }
                )
                digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
                if not hmac.compare_digest(digest, row["event_hash"]):
                    return False
                if not hmac.compare_digest(self._sign(digest), row["signature"]):
                    return False
                previous = digest
        return True

    def export_receipts(self, job_id: str) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            return [
                {
                    "id": row["id"],
                    "payload": _loads(row["payload_json"], {}),
                    "payload_sha256": row["payload_sha256"],
                    "signature": row["signature"],
                    "seal_valid": self._evidence_valid(row),
                }
                for row in connection.execute(
                    "SELECT * FROM evidence WHERE job_id=? AND kind='farmer_receipt' ORDER BY created_at",
                    (job_id,),
                )
            ]
