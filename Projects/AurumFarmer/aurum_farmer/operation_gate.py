"""Shared ingress admission and durable failure quarantine.

This gate verifies admission, never the success or safety of an arbitrary effect.
Executor authorization, independent result verification and LKG gates remain
mandatory. Only hashes of input, observations and results enter this journal.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import time
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any, Mapping

if __package__:
    from .decision_engine import DecisionEngine, digest
else:  # Transactionally installed Core worker modules.
    from decision_engine import DecisionEngine, digest


def source_revision(paths) -> str:
    """Observe implementation bytes, not mtimes or caller-supplied revisions."""
    return digest([(p.name, hashlib.sha256(p.read_bytes()).hexdigest())
                   for p in sorted(map(Path, paths))])


def workspace_revision(workspace: Path) -> str:
    """Observe code/configuration contents, including new unignored source files.

    Commit IDs, JSON receipts, Markdown notes and mtimes are deliberately absent.
    Adapters needing remote/device state must supply separate trusted observations.
    """
    patterns = ["*.py", "*.ps1", "*.sh", "*.js", "*.mjs", "*.cjs", "*.ts", "*.tsx",
                "*.c", "*.cpp", "*.h", "*.rs", "*.go", "*.toml", "*requirements*.txt",
                "*package*.json", "*.yaml", "*.yml", "*.ini", "*.cfg", "*.conf"]
    try:
        result = subprocess.run(["git", "-C", str(workspace), "ls-files", "--cached", "--others",
                                 "--exclude-standard", "-z", "--", *patterns],
                                capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return digest({"workspace": str(workspace.resolve()), "source_observation": type(error).__name__})
    observations = []
    if result.returncode == 0:
        for name in sorted(set(result.stdout.decode("utf-8", "surrogateescape").split("\0")) - {""}):
            path = workspace / name
            # Never follow a repository symlink into external private files.
            if path.is_symlink():
                observations.append((name, "symlink"))
            elif path.is_file():
                with path.open("rb") as handle:
                    observations.append((name, hashlib.file_digest(handle, "sha256").hexdigest()))
            else:
                observations.append((name, "missing"))
    return digest({"workspace": str(workspace.resolve()), "source_state": observations,
                   "git_status": result.returncode})


def semantic_input(value: Any) -> Any:
    """Ignore transport metadata, preserving all target IDs and action inputs."""
    if not isinstance(value, dict):
        return value
    return {k: v for k, v in value.items()
            if k not in {"request_id", "correlation_id", "idempotency_key", "client_timestamp"}}


class OperationGate:
    def __init__(self, path: Path, *, implementation: str, engine=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = engine or DecisionEngine()
        self.implementation = digest({"adapter": implementation,
                                      "gate": source_revision([Path(__file__)]),
                                      "engine": self.engine.implementation})
        with closing(self._connect()) as con, con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS future_operations(
                    fingerprint TEXT PRIMARY KEY, token TEXT NOT NULL,
                    state TEXT NOT NULL, decision_json TEXT NOT NULL,
                    outcome_digest TEXT, updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS future_operation_events(
                    sequence INTEGER PRIMARY KEY, fingerprint TEXT NOT NULL,
                    event TEXT NOT NULL, payload_json TEXT NOT NULL, created REAL NOT NULL);
            """)

    def _connect(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        return con

    @staticmethod
    def _event(con, fingerprint, event, payload):
        con.execute("INSERT INTO future_operation_events(fingerprint,event,payload_json,created) VALUES(?,?,?,?)",
                    (fingerprint, event, json.dumps(payload, sort_keys=True), time.time()))

    def begin(self, operation: str, inputs: Any, observed_state: Mapping[str, Any], *,
              recovery_observation: bool = False) -> dict[str, Any]:
        """Atomically admit once. Recovery observations never grant effect authority.

        recovery_observation is set by reviewed adapters for read-only diagnostics,
        polling and emergency stop, never from request body/header flags.
        """
        snapshot = {"operation": operation, "input_digest": digest(semantic_input(inputs)),
                    "observed_state_digest": digest(observed_state), "implementation": self.implementation}
        fingerprint = digest(snapshot)
        with closing(self._connect()) as con, con:
            con.execute("BEGIN IMMEDIATE")
            previous = con.execute("SELECT state FROM future_operations WHERE fingerprint=?", (fingerprint,)).fetchone()
            reason = None
            if previous and not recovery_observation:
                if previous["state"] == "running":
                    reason = "in_flight_or_unresolved_attempt"
                elif previous["state"] in {"failed", "uncertain"}:
                    reason = "unchanged_failed_operation"
            # The candidate is admission to the existing handler, not permission
            # to perform its side effects. That distinction is persisted explicitly.
            proposal = {"id": "admit", "executor": "existing_authorized_handler",
                        "payload": {"fingerprint": fingerprint}, "confidence": .5, "impact": .5,
                        "state": "QUARANTINED" if reason else "CANDIDATE",
                        "expected_evidence": [{"kind": "ingress_observation"}]}
            decision = self.engine.evaluate(snapshot, [proposal])
            allowed = decision["selected"] is not None and reason is None
            ticket = {"allowed": allowed, "fingerprint": fingerprint,
                      "state_id": decision["state_id"], "reason": reason,
                      "token": uuid.uuid4().hex if allowed else None}
            self._event(con, fingerprint, "decision", {"allowed": allowed, "reason": reason,
                        "scope": "admission_only", "dag": decision})
            if allowed:
                con.execute("""INSERT INTO future_operations VALUES(?,?,?, ?,NULL,?)
                    ON CONFLICT(fingerprint) DO UPDATE SET token=excluded.token,state=excluded.state,
                    decision_json=excluded.decision_json,outcome_digest=NULL,updated=excluded.updated""",
                    (fingerprint, ticket["token"], "running", json.dumps(decision, sort_keys=True), time.time()))
            return ticket

    def finish(self, ticket, outcome: str, evidence: Any) -> None:
        if outcome not in {"failed", "uncertain", "observed", "waiting", "refused"}:
            raise ValueError("ingress cannot claim verified completion")
        with closing(self._connect()) as con, con:
            updated = con.execute("""UPDATE future_operations SET state=?,outcome_digest=?,updated=?
                WHERE fingerprint=? AND token=? AND state='running'""",
                (outcome, digest(evidence), time.time(), ticket["fingerprint"], ticket["token"])).rowcount
            if updated:
                self._event(con, ticket["fingerprint"], "outcome", {"outcome": outcome,
                            "evidence_digest": digest(evidence), "verified_completion": False,
                            "lkg_promoted": False, "verifier": "ingress-observer-v1"})

    def status(self):
        with closing(self._connect()) as con:
            counts = {r["state"]: r["n"] for r in con.execute(
                "SELECT state,COUNT(*) AS n FROM future_operations GROUP BY state")}
            return {"engine": "aurum.future-branch.decision.v1", "default_on": True,
                    "scope": "admission_only", "implementation": self.implementation,
                    "operations": counts, "lkg_promoted": False}
