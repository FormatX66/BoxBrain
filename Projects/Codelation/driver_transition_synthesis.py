"""Deterministic, non-actuating state-transition synthesis for Aurum drivers.

This module learns transition rules from independent public/reference evidence and
verifies software-only traces. It never accesses physical hardware and never
performs MMIO/PIO, DMA, firmware, flash, clock, power, or persistent-device
writes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable

ALLOWED_SOURCE_KINDS = {
    "datasheet",
    "schematic",
    "reference_driver",
    "emulator",
    "firmware",
    "os_metadata",
    "errata",
    "observation",
}

TRANSITION_MODEL_SCHEMA = "aurum.hardware.transition-model.v0"
TRANSITION_CONTRACT_SCHEMA = "aurum.driver.transition-contract.v0"
TRANSITION_TRACE_SCHEMA = "aurum.driver.state-transition-trace.v0"
TRANSITION_VERIFICATION_SCHEMA = "aurum.driver.state-transition-verification.v0"
DEFAULT_PROMOTION_THRESHOLD = 2.0 / 3.0
MAX_TRACE_EVENTS = 4096
ALLOWED_TRACE_ORIGINS = {
    "reference-derived-synthetic",
    "emulator",
    "reference-driver-replay",
}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _identity(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TransitionClaim:
    key: str
    before: dict[str, Any]
    action: dict[str, Any]
    after: dict[str, Any]
    source_kind: str
    source_id: str
    confidence: float = 1.0

    def validate(self) -> None:
        if not isinstance(self.key, str) or not self.key.strip():
            raise ValueError("transition key is required")
        if self.source_kind not in ALLOWED_SOURCE_KINDS:
            raise ValueError(f"unsupported source kind: {self.source_kind}")
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("source id is required")
        if not all(isinstance(value, dict) for value in (self.before, self.action, self.after)):
            raise ValueError("before, action, and after must be objects")
        if not self.action or not isinstance(self.action.get("kind"), str) or not self.action["kind"]:
            raise ValueError("transition action kind is required")
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
            raise ValueError("confidence must be numeric")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        _canonical(self.before)
        _canonical(self.action)
        _canonical(self.after)

    def transition_value(self) -> dict[str, Any]:
        return {"before": self.before, "action": self.action, "after": self.after}


def reconcile_transition_evidence(
    claims: Iterable[TransitionClaim],
    *,
    promotion_threshold: float = DEFAULT_PROMOTION_THRESHOLD,
) -> dict[str, Any]:
    """Reconcile transition rules without letting duplicate source kinds outvote independence."""

    if not 0.5 <= promotion_threshold <= 1.0:
        raise ValueError("promotion threshold must be in [0.5, 1.0]")

    grouped: dict[str, list[TransitionClaim]] = {}
    for claim in claims:
        claim.validate()
        grouped.setdefault(claim.key, []).append(claim)

    modeled: dict[str, Any] = {}
    for key in sorted(grouped):
        by_value: dict[str, list[TransitionClaim]] = {}
        for claim in grouped[key]:
            by_value.setdefault(_canonical(claim.transition_value()), []).append(claim)

        candidates: list[dict[str, Any]] = []
        for canonical_value, same_value in by_value.items():
            strongest_by_kind: dict[str, float] = {}
            for claim in same_value:
                strongest_by_kind[claim.source_kind] = max(
                    strongest_by_kind.get(claim.source_kind, 0.0), float(claim.confidence)
                )
            candidates.append({
                "canonical_value": canonical_value,
                "transition": json.loads(canonical_value),
                "score": sum(strongest_by_kind.values()),
                "source_kinds": sorted(strongest_by_kind),
                "provenance": sorted([
                    {
                        "source_kind": claim.source_kind,
                        "source_id": claim.source_id,
                        "confidence": float(claim.confidence),
                    }
                    for claim in same_value
                ], key=lambda item: (item["source_kind"], item["source_id"])),
            })

        candidates.sort(key=lambda item: (-item["score"], item["canonical_value"]))
        total_score = sum(item["score"] for item in candidates)
        winner = candidates[0]
        confidence = winner["score"] / total_score if total_score else 0.0
        verified = confidence >= promotion_threshold and len(winner["source_kinds"]) >= 2
        modeled[key] = {
            "transition": winner["transition"] if verified else None,
            "candidate_transition": winner["transition"],
            "confidence": confidence,
            "state": "verified" if verified else "uncertain",
            "supporting_source_kinds": winner["source_kinds"],
            "provenance": winner["provenance"],
            "contradictions": [
                {
                    "transition": item["transition"],
                    "score": item["score"],
                    "source_kinds": item["source_kinds"],
                    "provenance": item["provenance"],
                }
                for item in candidates[1:]
            ],
        }

    model = {
        "schema": TRANSITION_MODEL_SCHEMA,
        "actuating": False,
        "transitions": modeled,
        "safety": {
            "hardware_access": False,
            "physical_writes_authorized": False,
            "firmware_changes_authorized": False,
        },
    }
    model["model_identity"] = _identity(model)
    return model


def synthesize_transition_contract(model: dict[str, Any]) -> dict[str, Any]:
    """Emit a non-executable transition contract from verified rules only."""

    if model.get("schema") != TRANSITION_MODEL_SCHEMA:
        raise ValueError("transition model schema mismatch")
    transitions = model.get("transitions")
    if not isinstance(transitions, dict):
        raise ValueError("transition model is missing transitions")

    resolved = {
        key: entry["transition"]
        for key, entry in sorted(transitions.items())
        if isinstance(entry, dict) and entry.get("state") == "verified"
    }
    contract = {
        "schema": TRANSITION_CONTRACT_SCHEMA,
        "model_identity": model.get("model_identity"),
        "mode": "non-actuating",
        "resolved_transitions": resolved,
        "required_validation": [
            "ordered-transition-replay",
            "counterfactual-mismatch-rejection",
            "scenario-continuity-check",
            "preserve-uncertain-transitions",
        ],
        "promotion_gates": {
            "physical_write_authorized": False,
            "firmware_change_authorized": False,
            "recovery_path_required_before_physical_actuation": True,
        },
    }
    contract["contract_identity"] = _identity(contract)
    return contract


def verify_transition_trace(model: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    """Verify an ordered software/reference trace against verified transition rules."""

    if model.get("schema") != TRANSITION_MODEL_SCHEMA:
        raise ValueError("transition model schema mismatch")
    if not isinstance(trace, dict) or trace.get("schema") != TRANSITION_TRACE_SCHEMA:
        raise ValueError("transition trace schema mismatch")
    if trace.get("actuating") is not False:
        raise ValueError("transition trace must be explicitly non-actuating")
    if trace.get("physical_hardware_observation") is not False:
        raise ValueError("this safety lane does not accept physical-hardware transition traces")
    if trace.get("origin") not in ALLOWED_TRACE_ORIGINS:
        raise ValueError("unsupported transition trace origin")
    if trace.get("model_identity") not in (None, model.get("model_identity")):
        raise ValueError("transition trace model identity mismatch")

    events = trace.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("transition trace events are required")
    if len(events) > MAX_TRACE_EVENTS:
        raise ValueError("transition trace exceeded event limit")

    transitions = model.get("transitions")
    if not isinstance(transitions, dict):
        raise ValueError("transition model is missing transitions")

    verified_keys = {
        key for key, entry in transitions.items()
        if isinstance(entry, dict) and entry.get("state") == "verified"
    }
    matched_keys: set[str] = set()
    previous_by_scenario: dict[str, tuple[int, dict[str, Any]]] = {}
    counts = {
        "matched": 0,
        "mismatched": 0,
        "uncertain": 0,
        "unknown": 0,
        "discontinuous": 0,
    }
    results: list[dict[str, Any]] = []

    expected_keys = {"scenario", "step", "transition_key", "before", "action", "after"}
    for event in events:
        if not isinstance(event, dict) or set(event) != expected_keys:
            raise ValueError("transition trace event shape mismatch")
        scenario = event["scenario"]
        step = event["step"]
        if not isinstance(scenario, str) or not scenario:
            raise ValueError("transition trace scenario is required")
        if isinstance(step, bool) or not isinstance(step, int) or step < 0:
            raise ValueError("transition trace step must be a non-negative integer")
        if not all(isinstance(event[name], dict) for name in ("before", "action", "after")):
            raise ValueError("transition trace states and action must be objects")
        if not isinstance(event["action"].get("kind"), str) or not event["action"]["kind"]:
            raise ValueError("transition trace action kind is required")

        prior = previous_by_scenario.get(scenario)
        discontinuous = False
        if prior is not None:
            prior_step, prior_after = prior
            if step <= prior_step:
                raise ValueError("transition trace steps must increase within each scenario")
            discontinuous = _canonical(prior_after) != _canonical(event["before"])
        previous_by_scenario[scenario] = (step, event["after"])

        key = event["transition_key"]
        entry = transitions.get(key) if isinstance(key, str) else None
        expected = entry.get("transition") if isinstance(entry, dict) else None
        observed = {"before": event["before"], "action": event["action"], "after": event["after"]}

        if not isinstance(entry, dict):
            outcome = "unknown"
        elif entry.get("state") != "verified":
            outcome = "uncertain"
            expected = entry.get("candidate_transition")
        elif _canonical(expected) != _canonical(observed):
            outcome = "mismatched"
        elif discontinuous:
            outcome = "discontinuous"
        else:
            outcome = "matched"
            matched_keys.add(key)

        counts[outcome] += 1
        results.append({
            "scenario": scenario,
            "step": step,
            "transition_key": key,
            "outcome": outcome,
            "expected_transition": expected,
            "observed_transition": observed,
        })

    coverage = len(matched_keys) / len(verified_keys) if verified_keys else 0.0
    missing_verified = sorted(verified_keys - matched_keys)
    passed = (
        bool(verified_keys)
        and coverage == 1.0
        and all(counts[name] == 0 for name in ("mismatched", "uncertain", "unknown", "discontinuous"))
    )
    status = "passed" if passed else (
        "failed" if counts["mismatched"] or counts["discontinuous"] else "incomplete"
    )

    verification = {
        "schema": TRANSITION_VERIFICATION_SCHEMA,
        "status": status,
        "actuating": False,
        "physical_hardware_proof": False,
        "model_identity": model.get("model_identity"),
        "trace_origin": trace.get("origin"),
        "verified_transition_coverage": coverage,
        "missing_verified_transitions": missing_verified,
        "counts": counts,
        "events": results,
        "safety": {
            "hardware_access_performed": False,
            "model_transitions_promoted": False,
            "physical_writes_authorized": False,
        },
    }
    verification["verification_identity"] = _identity(verification)
    return verification
