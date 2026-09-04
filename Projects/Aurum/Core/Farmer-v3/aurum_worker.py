#!/usr/bin/env python3
"""Aurum Farmer persistent worker.

The worker is deliberately event-driven. It does not poll or use a timer to make
progress. Durable Slush/Hive state is drained to quiescence at startup and after
every wake event. Payloads can invoke only reviewed, bounded tools; arbitrary
shell text is never executed.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get("AURUM_SLUSH_DB", str(ROOT / "slush.db")))
WAKE_SOCKET = Path(os.environ.get("AURUM_FARMER_SOCKET", str(DB.parent / "aurum-farmer.sock")))
DEFAULT_WORKSPACE = Path(os.environ.get("AURUM_WORKSPACE", str(ROOT)))

# Installed workers use the canonical module staged by the installer. Source
# checkouts import that same module directly, without maintaining a second copy.
try:
    from decision_engine import DecisionEngine, digest as decision_digest, score as decision_score
except ModuleNotFoundError as error:
    if error.name != "decision_engine":
        raise
    sys.path.insert(0, str(ROOT.parents[2] / "AurumFarmer"))
    from aurum_farmer.decision_engine import DecisionEngine, digest as decision_digest, score as decision_score

HUMAN_ONLY_BLOCKERS = {
    "physical_intervention",
    "secret_or_credential",
    "irreversible_external_approval",
    "legal_or_financial_approval",
    "ambiguous_human_preference",
}
REVERSIBILITY_WEIGHT = {"full": 1.0, "partial": 0.45, "none": 0.0}
SUCCESS_STATES = {"succeeded", "verified_completion"}
FAILURE_STATES = {"failed", "machine_blocked"}


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _decode_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, memoryview):
        raw = raw.tobytes()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "strict")
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, dict):
        raise ValueError("payload must be a JSON object")
    return raw


def _event_id(*parts: Any) -> str:
    body = ":".join(str(part) for part in parts)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:24]


def classify_blocker(blocker: Any) -> dict[str, Any]:
    if blocker is None:
        return {"blocked": False, "human_required": False, "kind": None}
    if isinstance(blocker, str):
        kind = blocker
    elif isinstance(blocker, dict):
        kind = str(blocker.get("kind") or blocker.get("type") or "machine_blocker")
    else:
        kind = "machine_blocker"
    return {"blocked": True, "human_required": kind in HUMAN_ONLY_BLOCKERS, "kind": kind}


def audit_completion(state: dict[str, Any]) -> dict[str, Any]:
    """Independent audit of the user's strict completion definition."""
    criteria = {
        "no_further_human_input": bool(state.get("no_further_human_input", False)),
        "no_known_bugs_or_glitches": bool(state.get("no_known_bugs_or_glitches", False)),
        "fully_functional": bool(state.get("fully_functional", False)),
        "no_required_changes_remaining": bool(state.get("no_required_changes_remaining", False)),
        "verification_passed": bool(state.get("verification_passed", False)),
    }
    blocker = classify_blocker(state.get("blocker"))
    complete = all(criteria.values()) and not blocker["blocked"]
    human_terminal = blocker["human_required"]
    return {
        "complete": complete,
        "criteria": criteria,
        "blocker": blocker,
        "terminal": complete or human_terminal,
        "terminal_state": (
            "verified_completion" if complete else "proven_human_only_blocker" if human_terminal else None
        ),
    }


def score_branch(branch: dict[str, Any]) -> float:
    reversibility = REVERSIBILITY_WEIGHT.get(str(branch.get("reversibility", "none")), 0.0)
    authority = 1.0 if branch.get("authority") == "authorized" else 0.0
    freshness = 1.0 if branch.get("fresh") is True else 0.0
    confidence = float(branch.get("confidence", 0.0))
    evidence = float(branch.get("evidence_quality", 0.0))
    risk = float(branch.get("risk", 1.0))
    cost = float(branch.get("cost", 1.0))
    impact = float(branch.get("impact", 0.5))
    return decision_score({"confidence": confidence, "impact": impact,
                           "evidence_quality": evidence, "risk": risk,
                           "irreversible_cost": float(branch.get("irreversible_cost", 0)),
                           "uncertainty": float(branch.get("uncertainty", 0))})


def choose_future_work(parameters: dict[str, Any]) -> dict[str, Any]:
    branches: list[dict[str, Any]] = []
    for raw in parameters.get("branches", []):
        if not isinstance(raw, dict):
            continue
        branch = dict(raw)
        branch["score"] = score_branch(branch)
        branches.append(branch)
    eligible = [
        branch
        for branch in branches
        if branch.get("authority") == "authorized"
        and branch.get("fresh") is True
        and float(branch.get("evidence_quality", 0.0)) >= 0.5
        and branch.get("reversibility") != "none"
        and float(branch.get("risk", 1)) <= .35
        and float(branch.get("irreversible_cost", 0)) == 0
        and float(branch["score"]) > 0
    ]
    eligible.sort(key=lambda b: (-float(b["score"]), str(b.get("id", ""))))
    threshold = float(parameters.get("ambiguity_threshold", 0.08))
    best = eligible[0] if eligible else None
    runner_up = eligible[1] if len(eligible) > 1 else None
    ambiguous = bool(
        best
        and runner_up
        and abs(float(best["score"]) - float(runner_up["score"])) <= threshold
    )
    promoted = None if ambiguous else best
    return {
        "decision": "promote_candidate" if promoted else "wait_for_evidence",
        "promoted_branch": promoted,
        "ambiguous": ambiguous,
        "branches": branches,
        "last_known_good": parameters.get("last_known_good"),
        "invariant": "last_known_good_remains_until_independent_verification",
    }


class FarmerWorker:
    def __init__(
        self,
        db_path: Path | str = DB,
        wake_socket: Path | str = WAKE_SOCKET,
        workspace: Path | str = DEFAULT_WORKSPACE,
    ) -> None:
        self.db_path = Path(db_path)
        self.wake_socket = Path(wake_socket)
        self.workspace = Path(workspace)
        self._stop = threading.Event()
        self._tools: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "echo": self._tool_echo,
            "audit_completion": self._tool_audit_completion,
            "future_branch": self._tool_future_branch,
            "repository_status": self._tool_repository_status,
            "run_checks": self._tool_run_checks,
            "farmer_plan": self._tool_farmer_plan,
        }
        self._ensure_schema()
        self.decision_engine = DecisionEngine()

    @contextmanager
    def _connect(self):
        con = sqlite3.connect(self.db_path, timeout=30)
        con.execute("PRAGMA journal_mode=WAL")
        try:
            with con:
                yield con
        finally:
            con.close()

    def _ensure_schema(self) -> None:
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS farmer_receipts(
                    directive_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    result TEXT NOT NULL,
                    human_required INTEGER NOT NULL DEFAULT 0,
                    created INTEGER NOT NULL
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS farmer_hive_receipts(
                    event_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    result TEXT NOT NULL,
                    human_required INTEGER NOT NULL DEFAULT 0,
                    created INTEGER NOT NULL
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS farmer_events(
                    event_id TEXT PRIMARY KEY,
                    directive_id TEXT,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created INTEGER NOT NULL
                )
                """
            )

    def _emit_event(self, directive_id: str | None, event_type: str, payload: dict[str, Any]) -> str:
        event_id = _event_id(time.time_ns(), directive_id, event_type, _json(payload))
        with self._connect() as con:
            con.execute(
                "INSERT INTO farmer_events(event_id,directive_id,event_type,payload,created) VALUES(?,?,?,?,?)",
                (event_id, directive_id, event_type, _json(payload), int(time.time())),
            )
        return event_id

    def _pending_slush(self) -> list[tuple[str, str, Any]]:
        with self._connect() as con:
            try:
                return con.execute(
                    """
                    SELECT hex(o.id), o.kind, o.payload
                    FROM objects o
                    JOIN tags t ON t.object_id=o.id
                    LEFT JOIN farmer_receipts r ON r.directive_id=hex(o.id)
                    WHERE t.tag IN ('tool-plan','self-development','directive')
                      AND r.directive_id IS NULL
                    ORDER BY o.updated ASC
                    """
                ).fetchall()
            except sqlite3.OperationalError:
                return []

    def _pending_hive(self) -> list[tuple[str, Any]]:
        with self._connect() as con:
            try:
                return con.execute(
                    """
                    SELECT e.event_id, e.payload
                    FROM hive_events e
                    LEFT JOIN farmer_hive_receipts r ON r.event_id=e.event_id
                    WHERE e.event_type='state_delta' AND r.event_id IS NULL
                    ORDER BY e.created ASC
                    """
                ).fetchall()
            except sqlite3.OperationalError:
                return []

    def _record_slush_receipt(self, directive_id: str, result: dict[str, Any]) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO farmer_receipts(directive_id,status,result,human_required,created)
                VALUES(?,?,?,?,?)
                """,
                (
                    directive_id,
                    str(result.get("status", "succeeded")),
                    _json(result),
                    1 if result.get("human_required") else 0,
                    int(time.time()),
                ),
            )

    def _record_hive_receipt(self, event_id: str, result: dict[str, Any]) -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO farmer_hive_receipts(event_id,status,result,human_required,created)
                VALUES(?,?,?,?,?)
                """,
                (
                    event_id,
                    str(result.get("status", "succeeded")),
                    _json(result),
                    1 if result.get("human_required") else 0,
                    int(time.time()),
                ),
            )

    def _dispatch(self, action: str, parameters: dict[str, Any]) -> dict[str, Any]:
        handler = self._tools.get(action)
        if handler is None:
            return {
                "status": "machine_blocked",
                "human_required": False,
                "blocker": {"kind": "unsupported_bounded_tool", "action": action},
            }
        snapshot = {"workspace": str(self.workspace.resolve()), "input_digest": decision_digest(parameters)}
        branch = {"id": action, "executor": action, "payload": {"input_digest": snapshot["input_digest"]},
                  "confidence": .8, "impact": .8, "expected_evidence": [{"kind": "bounded_tool_receipt"}]}
        decision = self.decision_engine.evaluate(snapshot, [branch])
        self._emit_event(None, "future_branch_decision", decision)
        if decision["selected"] is None:
            return {"status": "machine_blocked", "human_required": False,
                    "blocker": {"kind": "future_branch_gate", "state_id": decision["state_id"]}}
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="future-branch-explorer") as pool:
            exploration = pool.submit(self._explore_pending)
            result = handler(parameters)
            try:
                exploration.result()
            except Exception as error:
                # An observation/bookkeeping failure cannot reverse a completed
                # tool effect or cause it to be replayed as an execution failure.
                result["future_exploration_error"] = type(error).__name__
        outcome = result.get("status")
        accepted = outcome in SUCCESS_STATES and result.get("human_required") is False
        telemetry = {
            "state_id": decision["state_id"], "branch_id": action, "probability": .8,
            "outcome": outcome, "result_digest": decision_digest(result),
            "verification": "bounded_tool_contract", "verifier": "farmer-core-result-verifier-v1",
            "brier": (.8 - int(accepted)) ** 2 if outcome in SUCCESS_STATES | FAILURE_STATES else None,
            "lkg_promoted": False}
        try:
            self._emit_event(None, "future_branch_outcome", telemetry)
        except Exception as error:
            result["future_telemetry_error"] = type(error).__name__
        return result

    def _explore_pending(self):
        """Prepare pending ingress while current work executes; never drain it here."""
        pending = [(str(i), raw) for i, _kind, raw in self._pending_slush()]
        pending.extend((str(i), raw) for i, raw in self._pending_hive())
        if not pending:
            return
        branches = [{"id": identity, "executor": "ingress_observation",
                     "payload": {"input_digest": decision_digest(raw)},
                     "authority_ready": False, "expected_evidence": [{"kind": "ingress_receipt"}]}
                    for identity, raw in pending[:128]]
        report = self.decision_engine.evaluate({"pending_ingress": [b["payload"] for b in branches]}, branches,
                                               deepen=True)
        self._emit_event(None, "future_branch_pending", report)

    def _execute_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = str(payload.get("action") or payload.get("tool") or "farmer_plan")
        parameters = payload.get("parameters", payload if action == "farmer_plan" else {})
        if not isinstance(parameters, dict):
            raise ValueError("parameters must be an object")
        return self._dispatch(action, parameters)

    def process_slush_directive(self, directive_id: str, raw_payload: Any) -> dict[str, Any]:
        try:
            result = self._execute_payload(_decode_payload(raw_payload))
        except Exception as exc:
            result = {
                "status": "machine_blocked",
                "human_required": False,
                "blocker": {"kind": "worker_exception", "message": str(exc)[:1000]},
            }
        self._record_slush_receipt(directive_id, result)
        self._emit_event(directive_id, "directive_receipt", result)
        return result

    def process_hive_event(self, event_id: str, raw_payload: Any) -> dict[str, Any]:
        try:
            payload = _decode_payload(raw_payload)
            directive = payload.get("farmer_directive")
            if directive is None and payload.get("schema") == "aurum.farmer.directive.v1":
                directive = payload
            if isinstance(directive, dict):
                result = self._execute_payload(directive)
            else:
                result = {"status": "observed", "human_required": False, "reason": "no_farmer_directive"}
        except Exception as exc:
            result = {
                "status": "machine_blocked",
                "human_required": False,
                "blocker": {"kind": "hive_event_exception", "message": str(exc)[:1000]},
            }
        self._record_hive_receipt(event_id, result)
        self._emit_event(None, "hive_directive_receipt", {"source_event_id": event_id, **result})
        return result

    def drain(self) -> list[dict[str, Any]]:
        """Drain all currently durable work to quiescence without sleeping."""
        results: list[dict[str, Any]] = []
        while True:
            slush = self._pending_slush()
            hive = self._pending_hive()
            if not slush and not hive:
                break
            for directive_id, _kind, raw_payload in slush:
                result = self.process_slush_directive(directive_id, raw_payload)
                results.append({"directive_id": directive_id, **result})
            for event_id, raw_payload in hive:
                result = self.process_hive_event(event_id, raw_payload)
                results.append({"hive_event_id": event_id, **result})
        return results

    def _tool_echo(self, parameters: dict[str, Any]) -> dict[str, Any]:
        return {"status": "succeeded", "human_required": False, "message": str(parameters.get("message", ""))[:1000]}

    def _tool_audit_completion(self, parameters: dict[str, Any]) -> dict[str, Any]:
        audit = audit_completion(parameters)
        return {
            "status": audit["terminal_state"] or "succeeded",
            "human_required": audit["terminal_state"] == "proven_human_only_blocker",
            "audit": audit,
        }

    def _tool_future_branch(self, parameters: dict[str, Any]) -> dict[str, Any]:
        decision = choose_future_work(parameters)
        promoted = decision.get("promoted_branch")
        if isinstance(promoted, dict) and isinstance(promoted.get("action"), str):
            action_result = self._dispatch(
                promoted["action"],
                promoted.get("parameters") if isinstance(promoted.get("parameters"), dict) else {},
            )
            return {
                "status": action_result.get("status", "succeeded"),
                "human_required": bool(action_result.get("human_required", False)),
                "future_branch": decision,
                "action_result": action_result,
            }
        return {"status": "succeeded", "human_required": False, "future_branch": decision}

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.workspace,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "git failed").strip()[:1000])
        return result.stdout.strip()

    def _tool_repository_status(self, _parameters: dict[str, Any]) -> dict[str, Any]:
        if not (self.workspace / ".git").exists():
            return {
                "status": "machine_blocked",
                "human_required": False,
                "blocker": {"kind": "workspace_not_git_repository", "workspace": str(self.workspace)},
            }
        try:
            porcelain = self._git("status", "--porcelain=v1", "--untracked-files=no")
            return {
                "status": "succeeded",
                "human_required": False,
                "repository": {
                    "commit": self._git("rev-parse", "HEAD"),
                    "branch": self._git("branch", "--show-current") or "detached",
                    "tracked_worktree_clean": not bool(porcelain),
                    "changed_tracked_entries": 0 if not porcelain else len(porcelain.splitlines()),
                },
            }
        except Exception as exc:
            return {
                "status": "machine_blocked",
                "human_required": False,
                "blocker": {"kind": "repository_status_failed", "message": str(exc)[:1000]},
            }

    def _tool_run_checks(self, parameters: dict[str, Any]) -> dict[str, Any]:
        # Reviewed command IDs only. User/model payloads cannot inject shell text.
        commands: dict[str, list[str]] = {
            "python-unittest": [sys.executable, "-m", "unittest", "discover"],
            "python-pytest": [sys.executable, "-m", "pytest", "-q"],
            "npm-test": ["npm", "test"],
            "npm-check": ["npm", "run", "check"],
        }
        name = str(parameters.get("name", ""))
        command = commands.get(name)
        if command is None:
            return {
                "status": "machine_blocked",
                "human_required": False,
                "blocker": {"kind": "unsupported_check", "name": name},
            }
        timeout = max(1, min(int(parameters.get("timeout_seconds", 300)), 1800))
        try:
            result = subprocess.run(
                command,
                cwd=self.workspace,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except Exception as exc:
            return {
                "status": "machine_blocked",
                "human_required": False,
                "blocker": {"kind": "check_execution_failed", "message": str(exc)[:1000]},
            }
        evidence = (result.stdout + "\n" + result.stderr).strip()[-8000:]
        return {
            "status": "succeeded" if result.returncode == 0 else "failed",
            "human_required": False,
            "check": name,
            "returncode": result.returncode,
            "evidence": evidence,
        }

    def _tool_farmer_plan(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """Run execute/Future-Branch/recovery/verification cycles until a terminal condition."""
        completion_state = dict(parameters.get("completion", {})) if isinstance(parameters.get("completion", {}), dict) else {}
        raw_items = parameters.get("work_items", [])
        if not isinstance(raw_items, list):
            raise ValueError("work_items must be an array")

        items: dict[str, dict[str, Any]] = {}
        for index, raw in enumerate(raw_items):
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            item_id = str(item.get("id") or f"work-{index}")
            item["id"] = item_id
            item.setdefault("authority", "pending")
            item.setdefault("reversibility", "none")
            item.setdefault("fresh", False)
            item.setdefault("confidence", 0.0)
            item.setdefault("evidence_quality", 0.0)
            item.setdefault("risk", 1.0)
            item.setdefault("cost", 1.0)
            item.setdefault("impact", 0.5)
            item["score"] = score_branch(item)
            items[item_id] = item

        status_by_id: dict[str, str] = {}
        all_results: list[dict[str, Any]] = []
        max_parallel = max(1, min(int(parameters.get("max_parallel", 4)), 8))
        last_known_good = parameters.get("last_known_good")

        while True:
            audit = audit_completion(completion_state)
            if audit["terminal"]:
                return {
                    "status": audit["terminal_state"],
                    "human_required": audit["terminal_state"] == "proven_human_only_blocker",
                    "audit": audit,
                    "completion": completion_state,
                    "results": all_results,
                    "last_known_good": last_known_good,
                }

            ready: list[dict[str, Any]] = []
            for item_id, item in items.items():
                if item_id in status_by_id:
                    continue
                if item.get("authority") != "authorized" or item.get("fresh") is not True:
                    continue
                if float(item.get("evidence_quality", 0.0)) < 0.5 or item.get("reversibility") == "none":
                    continue
                if float(item.get("risk", 1)) > .35 or float(item.get("irreversible_cost", 0)) > 0 or item["score"] <= 0:
                    continue
                if not isinstance(item.get("action"), str):
                    continue
                deps = item.get("depends_on", [])
                if isinstance(deps, str):
                    deps = [deps]
                if deps and not all(status_by_id.get(str(dep)) in SUCCESS_STATES for dep in deps):
                    continue
                fallback_for = item.get("fallback_for")
                if fallback_for is not None and status_by_id.get(str(fallback_for)) not in FAILURE_STATES:
                    continue
                ready.append(item)

            if not ready:
                blocker = classify_blocker(parameters.get("blocker"))
                if blocker["human_required"]:
                    return {
                        "status": "proven_human_only_blocker",
                        "human_required": True,
                        "audit": audit,
                        "completion": completion_state,
                        "blocker": blocker,
                        "results": all_results,
                        "last_known_good": last_known_good,
                    }
                return {
                    "status": "machine_blocked",
                    "human_required": False,
                    "audit": audit,
                    "completion": completion_state,
                    "blocker": blocker if blocker["blocked"] else {"kind": "no_safe_ready_work"},
                    "results": all_results,
                    "last_known_good": last_known_good,
                }

            # Everything-all-at-once: independent safe work starts together.
            ready.sort(key=lambda item: (-float(item["score"]), str(item["id"])))
            with ThreadPoolExecutor(max_workers=min(max_parallel, len(ready)), thread_name_prefix="aurum-farmer") as pool:
                futures = {
                    pool.submit(
                        self._dispatch,
                        str(item["action"]),
                        item.get("parameters") if isinstance(item.get("parameters"), dict) else {},
                    ): item
                    for item in ready
                }
                cycle_results: list[tuple[dict[str, Any], dict[str, Any]]] = []
                for future in as_completed(futures):
                    item = futures[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = {
                            "status": "machine_blocked",
                            "human_required": False,
                            "blocker": {"kind": "parallel_action_exception", "message": str(exc)[:1000]},
                        }
                    cycle_results.append((item, result))

            for item, result in sorted(cycle_results, key=lambda pair: str(pair[0]["id"])):
                item_status = str(result.get("status") or "succeeded")
                status_by_id[str(item["id"])] = item_status
                all_results.append({"id": item["id"], "score": item["score"], **result})

                if bool(result.get("human_required", False)):
                    return {
                        "status": "proven_human_only_blocker",
                        "human_required": True,
                        "audit": audit_completion(completion_state),
                        "completion": completion_state,
                        "results": all_results,
                        "last_known_good": last_known_good,
                    }

                if item_status in SUCCESS_STATES:
                    updates = item.get("success_updates")
                    if isinstance(updates, dict):
                        completion_state.update(updates)
                    if item.get("establish_last_known_good"):
                        last_known_good = str(item["id"])
            # Immediate internal loop: audit -> Future Branch -> execute/recover -> verify.

    def serve_forever(self) -> None:
        if not hasattr(socket, "AF_UNIX"):
            raise RuntimeError("AF_UNIX is required for event-driven Aurum Farmer wake-up")
        self.drain()  # crash/reboot resume from durable state
        self.wake_socket.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.wake_socket.unlink(missing_ok=True)
        except TypeError:
            if self.wake_socket.exists():
                self.wake_socket.unlink()

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(self.wake_socket))
            os.chmod(self.wake_socket, 0o660)
            server.listen(16)
            while not self._stop.is_set():
                conn, _ = server.accept()  # OS event blocks here; no polling interval
                with conn:
                    raw = conn.recv(4096)
                    if raw:
                        try:
                            signal = json.loads(raw.decode("utf-8"))
                        except Exception:
                            signal = {"event": "wake"}
                        if not isinstance(signal, dict):
                            signal = {"event": "wake"}
                    else:
                        signal = {"event": "wake"}
                    wake_event_id = self._emit_event(None, "wake_signal", signal)
                    results = [] if self._stop.is_set() else self.drain()
                    acknowledgement = {
                        "status": "drained",
                        "wake_event_id": wake_event_id,
                        "processed": len(results),
                        "terminal_states": [
                            result.get("status") for result in results
                            if result.get("status") in {"verified_completion", "proven_human_only_blocker"}
                        ],
                    }
                    try:
                        conn.sendall(_json(acknowledgement).encode("utf-8"))
                    except OSError:
                        pass
        finally:
            server.close()
            try:
                self.wake_socket.unlink(missing_ok=True)
            except Exception:
                pass

    def stop(self) -> None:
        self._stop.set()
        signal_worker(self.wake_socket, {"event": "stop"})


def signal_worker(socket_path: Path | str = WAKE_SOCKET, event: dict[str, Any] | None = None) -> bool:
    if not hasattr(socket, "AF_UNIX"):
        return False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(1.0)
            client.connect(str(socket_path))
            client.sendall(_json(event or {"event": "state_changed"}).encode("utf-8"))
        return True
    except OSError:
        return False


if __name__ == "__main__":
    FarmerWorker().serve_forever()
