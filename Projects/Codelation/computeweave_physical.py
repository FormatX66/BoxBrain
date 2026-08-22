#!/usr/bin/env python3
"""Physical-node bridge for ComputeWeave.

This module lets trusted physical Aurum nodes advertise compute capacity and
accept the same deterministic shard contract used by hosted workers. It never
carries arbitrary shell commands: an orchestration request names a bounded
ComputeWeave operation plus workload identity and shard coordinates.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

PHYSICAL_NODE_SCHEMA = "aurum.computeweave-physical-node.v1"
PHYSICAL_REQUEST_SCHEMA = "aurum.computeweave-physical-request.v1"
PHYSICAL_RESULT_SCHEMA = "aurum.computeweave-physical-result.v1"
SHARD_SCHEMA = "aurum.computeweave-shard.v1"


@dataclass(frozen=True)
class Eligibility:
    eligible: bool
    reasons: tuple[str, ...]


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def assess_node(
    receipt: Mapping[str, Any],
    *,
    architecture: str = "any",
    max_heartbeat_age_seconds: int = 180,
    now: datetime | None = None,
) -> Eligibility:
    reasons: list[str] = []
    if receipt.get("schema") != PHYSICAL_NODE_SCHEMA:
        reasons.append("unsupported-schema")
    if not receipt.get("authorized", False):
        reasons.append("not-authorized")
    if not receipt.get("safe", False):
        reasons.append("unsafe")
    capabilities = set(receipt.get("capabilities") or ())
    if "computeweave-shard-v1" not in capabilities:
        reasons.append("missing-computeweave-capability")
    node_arch = str(receipt.get("architecture") or "any")
    if architecture != "any" and node_arch not in {"any", architecture}:
        reasons.append("architecture-mismatch")
    heartbeat = receipt.get("heartbeat_at")
    if not heartbeat:
        reasons.append("missing-heartbeat")
    else:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        age = (current - _timestamp(str(heartbeat))).total_seconds()
        if age < -30:
            reasons.append("heartbeat-from-future")
        elif age > max_heartbeat_age_seconds:
            reasons.append("stale-heartbeat")
    return Eligibility(not reasons, tuple(reasons))


def shard_request(
    *,
    request_id: str,
    source_sha: str,
    seed: str,
    units: int,
    rounds: int,
    shard_index: int,
    shard_count: int,
    target_node: str,
    architecture: str,
) -> dict[str, Any]:
    if shard_count < 1 or not 0 <= shard_index < shard_count:
        raise ValueError("invalid shard coordinates")
    return {
        "schema": PHYSICAL_REQUEST_SCHEMA,
        "operation": "computeweave-shard-v1",
        "request_id": request_id,
        "source_sha": source_sha,
        "target_node": target_node,
        "architecture": architecture,
        "workload": {
            "seed": seed,
            "units": units,
            "rounds": rounds,
            "shard_index": shard_index,
            "shard_count": shard_count,
        },
        "side_effects": "none",
        "physical_state_mutation_allowed": False,
    }


def validate_result(request: Mapping[str, Any], result: Mapping[str, Any]) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    if request.get("schema") != PHYSICAL_REQUEST_SCHEMA:
        reasons.append("unsupported-request-schema")
    if result.get("schema") != PHYSICAL_RESULT_SCHEMA:
        reasons.append("unsupported-result-schema")
    if result.get("request_id") != request.get("request_id"):
        reasons.append("request-id-mismatch")
    if result.get("source_sha") != request.get("source_sha"):
        reasons.append("source-sha-mismatch")
    if result.get("node") != request.get("target_node"):
        reasons.append("node-mismatch")
    if result.get("physical_state_mutated", False):
        reasons.append("physical-state-mutated")
    shard = result.get("shard")
    if not isinstance(shard, Mapping) or shard.get("schema") != SHARD_SCHEMA:
        reasons.append("invalid-shard-receipt")
    else:
        workload = request.get("workload") or {}
        comparisons = {
            "seed": workload.get("seed"),
            "units": workload.get("units"),
            "rounds": workload.get("rounds"),
            "shard_index": workload.get("shard_index"),
            "shard_count": workload.get("shard_count"),
        }
        for key, expected in comparisons.items():
            if shard.get(key) != expected:
                reasons.append(f"shard-{key}-mismatch")
        if shard.get("node") != result.get("node"):
            reasons.append("shard-node-mismatch")
        if not shard.get("verified", False):
            reasons.append("shard-not-verified")
    return not reasons, tuple(reasons)


__all__ = [
    "Eligibility",
    "PHYSICAL_NODE_SCHEMA",
    "PHYSICAL_REQUEST_SCHEMA",
    "PHYSICAL_RESULT_SCHEMA",
    "assess_node",
    "shard_request",
    "validate_result",
]
