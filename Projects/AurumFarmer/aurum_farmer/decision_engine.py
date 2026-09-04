"""Bounded Future Branch decision engine. Exploration never executes an action.

Inputs are observations, not authority. Trusted adapters supply probes; a proposal
cannot supply Python, commands, verifier identities, or passing test receipts.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

VERSION = "aurum.future-branch.decision.v1"
TIERS = ("static", "unit", "vm", "hardware_model", "canary")
QUALITY = {"static": 0.25, "unit": 0.5, "vm": 0.75, "hardware_model": 0.85, "canary": 1.0}
OUTCOMES = ("success", "degraded", "failure", "timeout", "no_change", "unexpected")


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False, default=str).encode()).hexdigest()


def score(branch: Mapping[str, Any], evidence_quality: float | None = None) -> float:
    """Keep probability, measured evidence, and safety as distinct inputs."""
    quality = float(branch.get("evidence_quality", 0)) if evidence_quality is None else evidence_quality
    return (float(branch.get("confidence", 0.5)) * float(branch.get("impact", 0.5)) * quality
            - float(branch.get("risk", 0)) - float(branch.get("irreversible_cost", 0))
            - float(branch.get("uncertainty", 0)))


@dataclass(frozen=True)
class Budget:
    nodes: int = 256
    workers: int = 4
    probe_units: int = 32
    # Successive halving spends progressively more on fewer candidates.
    tier_costs: tuple[int, ...] = (0, 1, 4, 8, 16)

    def __post_init__(self):
        if not 8 <= self.nodes <= 4096 or not 1 <= self.workers <= 16 or not 0 <= self.probe_units <= 4096:
            raise ValueError("invalid Future Branch resource budget")
        if len(self.tier_costs) != len(TIERS) or any(c < 1 for c in self.tier_costs[1:]):
            raise ValueError("verification tiers must have positive costs")


@dataclass(frozen=True)
class Probe:
    tier: str
    identity: str
    run: Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]]
    resource: str = "isolated"
    revision: str = "1"
    # Trusted probes must enforce a deadline internally (subprocess timeout for
    # command probes). Threads cannot safely cancel arbitrary Python callbacks.


class DecisionEngine:
    proposer = "future-branch-proposer-v1"
    verifier = "future-branch-static-verifier-v1"

    def __init__(self, *, budget: Budget | None = None, probes: tuple[Probe, ...] = ()):
        self.budget = budget or Budget()
        self.probes = {p.tier: p for p in probes}
        self.implementation = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        if len(self.probes) != len(probes):
            raise ValueError("one trusted probe per verification tier is required")
        for probe in probes:
            if probe.tier not in TIERS[1:] or probe.identity in {self.proposer, "farmer-executor", self.verifier}:
                raise ValueError("probe must be an independent verifier at a supported tier")

    @staticmethod
    def normalize(raw: Mapping[str, Any]) -> dict[str, Any]:
        b = dict(raw)
        for field, default in (("payload", {}), ("expected_evidence", []), ("human_boundary", None),
                               ("decision", {})):
            if field not in b:
                b[field] = json.loads(b.get(field + "_json") or json.dumps(default))
        b.update(b.pop("decision"))
        b["logical_id"] = str(b.get("logical_id", b.get("id", "")))
        fields = {"logical_id", "executor", "payload", "expected_evidence", "human_boundary",
                  "confidence", "impact", "evidence_quality", "risk", "cost", "reversibility",
                  "authority_ready", "dependencies_satisfied", "lkg_scope", "state", "failure_fingerprint",
                  "parents", "required_tier", "effect", "rollback_ref", "expires_at", "uncertainty",
                  "irreversible_cost", "impossible", "implementation_ref", "eligible_after",
                  "attempt_count", "max_attempts"}
        return {k: v for k, v in b.items() if k in fields}

    def evaluate(self, snapshot: Mapping[str, Any], proposals: list[Mapping[str, Any]], *,
                 deepen: bool = False, prior: Mapping[str, Any] | None = None) -> dict[str, Any]:
        branches = [self.normalize(b) for b in proposals]
        if len({b["logical_id"] for b in branches}) != len(branches):
            raise ValueError("duplicate candidate IDs")
        # No wall clock/heartbeat in the identity. Identical semantic input reuses work.
        state_id = digest({"version": VERSION, "implementation": self.implementation,
                           "probes": [(p.tier, p.identity, p.resource, p.revision) for p in self.probes.values()],
                           "state": snapshot, "branches": branches})
        if prior and prior.get("state_id") != state_id:
            prior = None
        nodes = [{"id": "state", "kind": "observed_state", "state_id": state_id, "parents": []},
                 {"id": "hold", "kind": "control", "parents": ["state"], "automatic": False},
                 {"id": "lkg", "kind": "protected_lkg", "parents": ["state"],
                  "references": snapshot.get("lkg", {}), "automatic": False}]
        reports = []
        by_id = {b["logical_id"]: b for b in branches}
        seen: dict[str, str] = {}
        visiting: set[str] = set()
        visited: set[str] = set()

        def dag_ok(name: str) -> bool:
            if name in visiting or name not in by_id:
                return False
            if name in visited:
                return True
            visiting.add(name)
            ok = all(dag_ok(str(p)) for p in by_id[name].get("parents", []))
            visiting.remove(name)
            if ok:
                visited.add(name)
            return ok

        prior_branches = {b["id"]: b for b in (prior or {}).get("branches", [])}
        for b in branches:
            name = b["logical_id"]
            reason = None
            values = [float(b.get(k, default)) for k, default in
                      (("confidence", .5), ("impact", .5), ("risk", 0), ("reversibility", 1),
                       ("evidence_quality", .5), ("uncertainty", 0), ("irreversible_cost", 0))]
            if not name or not all(math.isfinite(v) and 0 <= v <= 1 for v in values):
                reason = "invalid_estimate"
            elif not dag_ok(name):
                reason = "invalid_dag"
            elif b.get("state") in {"QUARANTINED", "SUCCEEDED"}:
                reason = b["state"].lower()
            elif int(b.get("attempt_count", 0)) >= int(b.get("max_attempts", 20)):
                reason = "attempts_exhausted"
            elif b.get("impossible"):
                reason = "impossible"
            elif not b.get("authority_ready", True) or b.get("human_boundary"):
                reason = "authority_boundary"
            elif not b.get("dependencies_satisfied", True):
                reason = "dependency"
            elif float(b.get("eligible_after") or 0) > time.time():
                reason = "retry_not_due"
            elif b.get("parents") and not all(by_id[p].get("state") == "SUCCEEDED" for p in b["parents"]):
                reason = "parent_not_verified"
            elif b.get("expires_at") is not None and float(b["expires_at"]) <= time.time():
                reason = "expired"
            elif float(b.get("risk", 0)) > .35 or float(b.get("reversibility", 1)) < .9 or float(b.get("irreversible_cost", 0)) > 0:
                reason = "protected_effect"
            elif not b.get("expected_evidence"):
                reason = "missing_evidence_contract"
            action_id = digest({k: b.get(k) for k in ("executor", "payload", "parents", "lkg_scope",
                                                     "expected_evidence", "authority_ready", "human_boundary")})
            if not reason and action_id in seen:
                reason = "redundant:" + seen[action_id]
            elif not reason:
                seen[action_id] = name
            tests = [{"tier": "static", "verifier": self.verifier, "passed": reason is None,
                      "evidence_ref": digest({"state": state_id, "action": action_id, "reason": reason})}]
            if name in prior_branches:
                tests.extend(t for t in prior_branches[name]["tests"] if t["tier"] != "static")
            required = b.get("required_tier", "static")
            if required not in TIERS:
                reason = "invalid_verification_tier"
            # Any state-changing candidate requires a tested rollback path and at
            # least unit evidence. A caller cannot lower this using required_tier.
            if b.get("effect", "read_only") != "read_only":
                required = required if required in TIERS[1:] else "unit"
                if not b.get("lkg_scope") or not snapshot.get("lkg", {}).get(b["lkg_scope"]):
                    reason = reason or "missing_lkg"
                if not b.get("rollback_ref"):
                    reason = reason or "missing_rollback"
            reports.append({"id": name, "action_id": action_id, "reason": reason,
                            "required_tier": required, "tests": tests, "automatic": False,
                            "probability": float(b.get("confidence", .5)), "executor": b.get("executor"),
                            "score": 0.0})
        spent = 0
        survivors = [r for r in reports if not r["reason"]]
        if deepen:
            for level, tier in enumerate(TIERS[1:], 1):
                probe = self.probes.get(tier)
                if not probe:
                    break  # No skipping unavailable verification layers.
                contenders = [r for r in survivors if all(t["passed"] for t in r["tests"])
                              and not any(t["tier"] == tier for t in r["tests"])
                              and set(TIERS[:level]) <= {t["tier"] for t in r["tests"] if t["passed"]}]
                contenders.sort(key=lambda r: (-score(by_id[r["id"]], QUALITY[TIERS[level-1]]), r["id"]))
                slots = min(max(1, len(survivors) // (2 ** (level - 1))),
                            (self.budget.probe_units - spent) // self.budget.tier_costs[level])
                contenders = contenders[:slots]
                if not contenders:
                    continue

                def check(r):
                    try:
                        receipt = dict(probe.run(snapshot, by_id[r["id"]]))
                        passed = receipt.get("passed") is True and bool(receipt.get("evidence_ref"))
                        return {"tier": tier, "verifier": probe.identity, "passed": passed,
                                "rollback_verified": receipt.get("rollback_verified") is True,
                                "evidence_ref": str(receipt.get("evidence_ref", "")),
                                "receipt_digest": digest(receipt)}
                    except Exception as exc:
                        return {"tier": tier, "verifier": probe.identity, "passed": False,
                                "error": type(exc).__name__, "evidence_ref": ""}

                # Hardware resources are exclusive. Isolated CPU/VM probes may fan out.
                workers = self.budget.workers if probe.resource == "isolated" else 1
                with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="future-verify") as pool:
                    for r, receipt in zip(contenders, pool.map(check, contenders)):
                        r["tests"].append(receipt)
                        spent += self.budget.tier_costs[level]
                        if not receipt["passed"]:
                            r["reason"] = "verification_failed:" + tier
        for r in reports:
            b = by_id[r["id"]]
            passed = {t["tier"] for t in r["tests"] if t["passed"]}
            quality = max((QUALITY[t] for t in passed), default=0)
            r["evidence_quality"] = quality
            r["score"] = score(b, quality) if all(math.isfinite(v) for v in
                (float(b.get("confidence", .5)), float(b.get("impact", .5)), float(b.get("risk", 0)),
                 float(b.get("irreversible_cost", 0)), float(b.get("uncertainty", 0)))) else -1.0
            if any(not t["passed"] for t in r["tests"][1:]):
                r["reason"] = r["reason"] or "verification_failed"
            if not r["reason"] and r["required_tier"] not in passed:
                r["reason"] = "verification_pending:" + r["required_tier"]
            if not r["reason"] and b.get("effect", "read_only") != "read_only" and not any(
                    t.get("passed") and t.get("rollback_verified") for t in r["tests"]):
                r["reason"] = "rollback_not_verified"
            r["automatic"] = r["reason"] is None and r["score"] > 0
            if not r["reason"] and not r["automatic"]:
                r["reason"] = "nonpositive_value"
            if len(nodes) < self.budget.nodes:
                nodes.append({"id": "action:" + r["id"], "kind": "candidate", "branch_id": r["id"],
                              "parents": (["action:" + p for p in b.get("parents", [])]
                                          if dag_ok(r["id"]) else []) or ["state"],
                              "pruned": r["reason"], "automatic": r["automatic"]})
        # Expand outcome and recovery/verification successors only within a hard cap.
        # These predictions carry zero execution authority, even when a parent wins.
        for r in sorted(reports, key=lambda r: -r["score"]):
            if not any(n["id"] == "action:" + r["id"] for n in nodes):
                continue
            for outcome in OUTCOMES:
                if len(nodes) + 2 > self.budget.nodes:
                    break
                name = r["id"] + ":" + outcome
                nodes.append({"id": name, "kind": "prediction", "outcome": outcome,
                              "parents": ["action:" + r["id"]], "automatic": False})
                nodes.append({"id": name + ":next", "kind": "verify" if outcome == "success" else "recover",
                              "parents": [name, "lkg"], "automatic": False})
        eligible = sorted((r for r in reports if r["automatic"]), key=lambda r: (-r["score"], r["id"]))
        ambiguous = len(eligible) > 1 and abs(eligible[0]["score"] - eligible[1]["score"]) <= .01
        return {"schema": VERSION, "state_id": state_id, "proposer": self.proposer,
                "executor": "farmer-executor", "nodes": nodes, "branches": reports,
                "selected": eligible[0]["id"] if eligible and not ambiguous else None,
                "status": "ambiguous" if ambiguous else "eligible" if eligible else "waiting",
                "probe_units": spent, "node_budget": self.budget.nodes,
                "available_tiers": ["static", *self.probes], "lkg_preserved": True}
