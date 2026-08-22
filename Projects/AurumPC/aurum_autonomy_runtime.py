#!/usr/bin/env python3
"""Aurum machine-speed autonomy envelope and path selection runtime.

The capability graph answers what could work. This module answers which paths
Aurum may try without interrupting a human, then biases future choices using
measured receipts.

This runtime does not provide arbitrary command execution. It produces bounded
decisions: AUTO, ESCALATE, or DENY. A separate actuator registry must implement
specific reversible operations.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from aurum_capability_graph import plan_intent

ENVELOPE_SCHEMA = "aurum.autonomy-envelope.v1"
DECISION_SCHEMA = "aurum.autonomy-decision.v1"
HISTORY_SCHEMA = "aurum.path-history.v1"
DEFAULT_ENVELOPE_PATH = Path(
    os.environ.get("AURUM_AUTONOMY_ENVELOPE", "/var/lib/aurum/state/autonomy-envelope.json")
)
DEFAULT_HISTORY_PATH = Path(
    os.environ.get("AURUM_PATH_HISTORY", "/var/lib/aurum/state/path-history.json")
)

AUTO = "AUTO"
ESCALATE = "ESCALATE"
DENY = "DENY"


def default_envelope() -> dict[str, Any]:
    """Return a conservative but useful first autonomy envelope.

    The defaults are intentionally permissive for observation, comparison,
    retries and reversible recovery on local/authorized resources, while new
    privacy, ownership, cost, destructive and trust boundaries still escalate.
    """
    return {
        "schema": ENVELOPE_SCHEMA,
        "revision": 1,
        "principle": "humans approve boundaries; machines choose paths",
        "auto_action_classes": [
            "observe",
            "measure",
            "compare",
            "select",
            "probe-bounded",
            "retry-bounded",
            "reroute",
            "transport-switch",
            "recover-reversible",
            "compute-local",
            "compute-remote-authorized",
            "state-replicate-authorized",
            "sensor-read-authorized",
            "notify-authorized",
        ],
        "deny_action_classes": [
            "firmware-write-unbounded",
            "fuse-write",
            "raw-voltage-control",
            "raw-clock-control",
            "unsafe-thermal-control",
            "destructive-storage",
            "credential-bypass",
            "trust-boundary-weaken",
        ],
        "observe_unverified_devices": True,
        "actuate_unverified_devices": False,
        "allow_privacy_sensitive_auto": False,
        "allow_health_sensitive_auto": False,
        "allow_new_person_scope_auto": False,
        "allow_new_account_scope_auto": False,
        "allow_irreversible_auto": False,
        "allow_destructive_auto": False,
        "allow_external_physical_effect_auto": False,
        "max_auto_monetary_cost": 0.0,
        "max_auto_risk": "low",
        "authorized_scopes": ["local", "authorized-peer", "authorized-network", "authorized-cloud"],
        "guarded_auto_action_classes": ["observe", "measure", "compare", "select"],
    }


def empty_history() -> dict[str, Any]:
    return {
        "schema": HISTORY_SCHEMA,
        "updated_at": None,
        "paths": {},
    }


def _risk_value(value: object) -> int:
    return {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}.get(
        str(value or "low").lower(), 3
    )


def _scope_for(node: dict[str, Any], intent: dict[str, Any]) -> str:
    if intent.get("scope"):
        return str(intent["scope"])
    properties = node.get("properties") or {}
    authorization = str(properties.get("authorization") or "").lower()
    if node.get("source") == "network-discovery":
        if authorization in {"authorized", "owned", "trusted"}:
            return "authorized-network"
        return "unverified-network"
    if node.get("source") in {"peer", "aurum-peer"}:
        return "authorized-peer" if authorization in {"authorized", "owned", "trusted"} else "unverified-peer"
    if node.get("source") in {"cloud", "compute-cloud"}:
        return "authorized-cloud" if authorization in {"authorized", "owned", "trusted"} else "unverified-cloud"
    return "local"


def evaluate_candidate(
    node: dict[str, Any],
    intent: dict[str, Any],
    envelope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate one capability node against the human-approved envelope."""
    envelope = envelope or default_envelope()
    action_class = str(intent.get("action_class") or "observe")
    scope = _scope_for(node, intent)
    reasons: list[str] = []

    if action_class in set(envelope.get("deny_action_classes") or []):
        return {
            "decision": DENY,
            "action_class": action_class,
            "scope": scope,
            "reasons": ["action-class-denied"],
        }

    if bool(intent.get("destructive")) and not envelope.get("allow_destructive_auto", False):
        reasons.append("destructive-boundary")
    if bool(intent.get("irreversible")) and not envelope.get("allow_irreversible_auto", False):
        reasons.append("irreversibility-boundary")
    if bool(intent.get("privacy_sensitive")) and not envelope.get("allow_privacy_sensitive_auto", False):
        reasons.append("privacy-boundary")
    if bool(intent.get("health_sensitive")) and not envelope.get("allow_health_sensitive_auto", False):
        reasons.append("health-data-boundary")
    if bool(intent.get("new_person_scope")) and not envelope.get("allow_new_person_scope_auto", False):
        reasons.append("new-person-boundary")
    if bool(intent.get("new_account_scope")) and not envelope.get("allow_new_account_scope_auto", False):
        reasons.append("new-account-boundary")
    if bool(intent.get("external_physical_effect")) and not envelope.get(
        "allow_external_physical_effect_auto", False
    ):
        reasons.append("external-physical-effect-boundary")

    monetary_cost = float(intent.get("monetary_cost") or 0.0)
    if monetary_cost > float(envelope.get("max_auto_monetary_cost") or 0.0):
        reasons.append("cost-boundary")

    if _risk_value(intent.get("risk")) > _risk_value(envelope.get("max_auto_risk")):
        reasons.append("risk-boundary")

    authorized_scopes = set(envelope.get("authorized_scopes") or [])
    unverified = scope.startswith("unverified-")
    if unverified:
        if action_class in {"observe", "measure", "compare", "select", "probe-bounded"} and envelope.get(
            "observe_unverified_devices", True
        ):
            reasons.append("unverified-observation-only")
        else:
            reasons.append("authorization-boundary")
    elif scope not in authorized_scopes:
        reasons.append("scope-boundary")

    if node.get("safety") == "guarded" and action_class not in set(
        envelope.get("guarded_auto_action_classes") or []
    ):
        reasons.append("guarded-resource-boundary")

    if reasons:
        return {
            "decision": ESCALATE,
            "action_class": action_class,
            "scope": scope,
            "reasons": reasons,
        }

    if action_class not in set(envelope.get("auto_action_classes") or []):
        return {
            "decision": ESCALATE,
            "action_class": action_class,
            "scope": scope,
            "reasons": ["action-class-not-preauthorized"],
        }

    return {
        "decision": AUTO,
        "action_class": action_class,
        "scope": scope,
        "reasons": ["inside-autonomy-envelope"],
    }


def _history_key(node_id: str, action_class: str) -> str:
    return f"{action_class}|{node_id}"


def _history_adjustment(
    history: dict[str, Any], node_id: str, action_class: str
) -> tuple[float, list[str]]:
    stats = (history.get("paths") or {}).get(_history_key(node_id, action_class)) or {}
    attempts = int(stats.get("attempts") or 0)
    if attempts <= 0:
        return 0.0, []

    successes = int(stats.get("successes") or 0)
    reliability = successes / attempts
    adjustment = (reliability - 0.5) * min(24.0, 4.0 + attempts * 2.0)
    reasons = [f"measured-reliability:{reliability:.3f}", f"attempts:{attempts}"]

    latency_ms = stats.get("latency_ewma_ms")
    if isinstance(latency_ms, (int, float)):
        if latency_ms <= 50:
            adjustment += 4.0
            reasons.append("measured-latency:very-low")
        elif latency_ms <= 250:
            adjustment += 2.0
            reasons.append("measured-latency:low")
        elif latency_ms >= 5000:
            adjustment -= 3.0
            reasons.append("measured-latency:high")

    return adjustment, reasons


def plan_with_envelope(
    graph: dict[str, Any],
    intent: dict[str, Any],
    *,
    envelope: dict[str, Any] | None = None,
    history: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Rank capability paths, apply the envelope, and choose without needless human gates."""
    envelope = envelope or default_envelope()
    history = history or empty_history()
    base = plan_intent(graph, intent)
    by_id = {node.get("id"): node for node in graph.get("nodes") or []}
    action_class = str(intent.get("action_class") or "observe")
    candidates: list[dict[str, Any]] = []

    for candidate in base.get("candidates") or []:
        node = by_id.get(candidate.get("node_id")) or {}
        policy = evaluate_candidate(node, intent, envelope)
        history_delta, history_reasons = _history_adjustment(
            history, str(candidate.get("node_id")), action_class
        )
        item = dict(candidate)
        item["base_score"] = float(candidate.get("score") or 0.0)
        item["history_adjustment"] = round(history_delta, 3)
        item["score"] = round(item["base_score"] + history_delta, 3)
        item["policy"] = policy
        item["execution_authorized"] = policy["decision"] == AUTO
        item["reasons"] = list(item.get("reasons") or []) + history_reasons + policy["reasons"]
        candidates.append(item)

    decision_rank = {AUTO: 0, ESCALATE: 1, DENY: 2}
    candidates.sort(
        key=lambda item: (
            decision_rank.get(item["policy"]["decision"], 9),
            -float(item.get("score") or 0.0),
            str(item.get("node_id") or ""),
        )
    )

    auto_candidates = [item for item in candidates if item["policy"]["decision"] == AUTO]
    escalation_candidates = [item for item in candidates if item["policy"]["decision"] == ESCALATE]
    selected = auto_candidates[0] if auto_candidates else None
    escalation = escalation_candidates[0] if not selected and escalation_candidates else None

    return {
        "schema": DECISION_SCHEMA,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "intent": intent,
        "candidate_count": len(candidates),
        "auto_candidate_count": len(auto_candidates),
        "selected": selected,
        "escalation_candidate": escalation,
        "decision": AUTO if selected else (ESCALATE if escalation else DENY),
        "human_interrupt_required": selected is None and escalation is not None,
        "execution_authorized": selected is not None,
        "candidates": candidates,
        "principle": "do not ask permission for every path; ask when the boundary changes",
    }


def record_receipt(history: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    """Fold one measured path outcome into compact reliability/timing history."""
    node_id = str(receipt["node_id"])
    action_class = str(receipt.get("action_class") or "observe")
    key = _history_key(node_id, action_class)
    paths = history.setdefault("paths", {})
    stats = dict(paths.get(key) or {})

    attempts = int(stats.get("attempts") or 0) + 1
    success = bool(receipt.get("success"))
    stats["attempts"] = attempts
    stats["successes"] = int(stats.get("successes") or 0) + (1 if success else 0)
    stats["failures"] = int(stats.get("failures") or 0) + (0 if success else 1)
    stats["last_success"] = success
    stats["last_observed_at"] = receipt.get("observed_at") or time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
    )

    for field in ("latency_ms", "queue_delay_ms", "execution_ms"):
        value = receipt.get(field)
        if not isinstance(value, (int, float)):
            continue
        ewma_field = field.replace("latency_ms", "latency_ewma_ms").replace(
            "queue_delay_ms", "queue_delay_ewma_ms"
        ).replace("execution_ms", "execution_ewma_ms")
        prior = stats.get(ewma_field)
        stats[ewma_field] = round(float(value) if prior is None else (0.7 * float(prior) + 0.3 * float(value)), 3)

    paths[key] = stats
    history["schema"] = HISTORY_SCHEMA
    history["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return history


def _load_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback
    return payload if isinstance(payload, dict) else fallback


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Aurum autonomy envelope runtime")
    sub = parser.add_subparsers(dest="command", required=True)

    emit = sub.add_parser("default-envelope")
    emit.add_argument("--out", type=Path, default=DEFAULT_ENVELOPE_PATH)

    decide = sub.add_parser("decide")
    decide.add_argument("--graph", type=Path, required=True)
    decide.add_argument("--intent", type=Path, required=True)
    decide.add_argument("--envelope", type=Path, default=DEFAULT_ENVELOPE_PATH)
    decide.add_argument("--history", type=Path, default=DEFAULT_HISTORY_PATH)

    receipt = sub.add_parser("receipt")
    receipt.add_argument("--receipt", type=Path, required=True)
    receipt.add_argument("--history", type=Path, default=DEFAULT_HISTORY_PATH)

    args = parser.parse_args()

    if args.command == "default-envelope":
        payload = default_envelope()
        _atomic_json(args.out, payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.command == "decide":
        graph = _load_json(args.graph, {})
        intent = _load_json(args.intent, {})
        envelope = _load_json(args.envelope, default_envelope())
        history = _load_json(args.history, empty_history())
        decision = plan_with_envelope(graph, intent, envelope=envelope, history=history)
        print(json.dumps(decision, indent=2, sort_keys=True))
        return 0 if decision.get("decision") == AUTO else 2

    history = _load_json(args.history, empty_history())
    receipt_payload = _load_json(args.receipt, {})
    updated = record_receipt(history, receipt_payload)
    _atomic_json(args.history, updated)
    print(json.dumps(updated, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
