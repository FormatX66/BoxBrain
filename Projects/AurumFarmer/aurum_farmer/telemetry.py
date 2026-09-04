"""Read-only, redacted projection of sealed Future Branch decisions."""
from contextlib import closing
import hmac
import json
import time

from .decision_engine import digest
from .ledger import LedgerError


def exploration_status(ledger):
    explorer = getattr(ledger, 'failure_explorer', None)
    if explorer is None:
        return {'schema': 'aurum.future-branch.continuous.v1', 'mode': 'not_attached', 'healthy': False}
    status = explorer.status()
    return {k: v for k, v in status.items() if k not in {'owner', 'pid'}}


def monitor_snapshot(ledger):
    stats = ledger.stats()
    traces = []
    with closing(ledger._connect()) as con:
        stamps = {json.loads(r["payload_json"]).get("report_sha256"): r["created_at"] for r in con.execute(
            "SELECT payload_json,created_at FROM events WHERE entity_type='future_branch' AND event_type='decision' ORDER BY sequence DESC LIMIT 100")}
        for row in con.execute("SELECT * FROM future_decisions ORDER BY sequence DESC LIMIT 20"):
            report = json.loads(row["report_json"])
            if digest(report) != row["report_hash"] or not hmac.compare_digest(ledger._sign(row["report_hash"]), row["signature"]):
                raise LedgerError("decision integrity check failed")
            names = {b["id"]: "Branch " + str(i + 1) for i, b in enumerate(report["branches"])}
            branches = []
            for b in sorted(report["branches"], key=lambda b: (b["id"] != report["selected"], -b["score"]))[:16]:
                branches.append({"label": names[b["id"]], "selected": b["id"] == report["selected"],
                    "score": b["score"], "evidence_quality": b["evidence_quality"],
                    "automatic": b["automatic"], "reason": str(b["reason"] or "eligible").split(":", 1)[0],
                    "required_tier": b["required_tier"],
                    "checks": [{"tier": t["tier"], "passed": t["passed"]} for t in b["tests"]]})
            traces.append({"sequence": row["sequence"], "state_id": row["state_id"],
                "observed_at": stamps.get(row["report_hash"]), "seal_valid": True,
                "status": report["status"], "selected": names.get(report["selected"]),
                "candidate_count": len(report["branches"]), "node_count": len(report["nodes"]),
                "probe_units": report["probe_units"], "branches": branches,
                "lkg_preserved": report["lkg_preserved"]})
    return {"schema": "aurum.future-branch.monitor.v1", "observed_at": time.time(),
            "status": "healthy" if stats["event_chain_valid"] else "integrity_failure",
            "activity": "executing" if stats["running_attempts"] else "idle",
            "event_chain_valid": stats["event_chain_valid"], "running_attempts": stats["running_attempts"],
            "job_states": stats["states"], "future_branch": stats["future_branch"], "recent_decisions": traces,
            "continuous_exploration": exploration_status(ledger),
            "scope": "Farmer runtime only; chat reports are separate evidence", "read_only": True}
