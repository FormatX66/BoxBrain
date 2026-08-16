"""Deterministic, non-actuating hardware evidence reconciliation for Aurum.

This module is the safe first stage of Autonomous Driver Synthesis. It does not
access hardware and cannot perform MMIO/PIO, DMA, firmware, flash, power, clock,
or other device writes. It only reconciles bounded evidence into a provenance-
preserving behavioral model and emits a non-actuating candidate interface
manifest for later emulation/verification.
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
    "firmware",
    "os_metadata",
    "errata",
    "observation",
}

MODEL_SCHEMA = "aurum.hardware.behavior-model.v0"
CANDIDATE_SCHEMA = "aurum.driver.candidate-interface.v0"
DEFAULT_PROMOTION_THRESHOLD = 2.0 / 3.0


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _identity(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EvidenceClaim:
    key: str
    value: Any
    source_kind: str
    source_id: str
    confidence: float = 1.0

    def validate(self) -> None:
        if not isinstance(self.key, str) or not self.key.strip():
            raise ValueError("claim key is required")
        if self.source_kind not in ALLOWED_SOURCE_KINDS:
            raise ValueError(f"unsupported source kind: {self.source_kind}")
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("source id is required")
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
            raise ValueError("confidence must be numeric")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        _canonical(self.value)


def reconcile_evidence(
    claims: Iterable[EvidenceClaim],
    *,
    promotion_threshold: float = DEFAULT_PROMOTION_THRESHOLD,
) -> dict[str, Any]:
    """Build a deterministic confidence-scored model from independent evidence.

    Repeated claims from the same source kind cannot overwhelm independent
    evidence: for each candidate value, only the strongest claim from each
    source kind contributes to the score. All provenance and contradictions are
    still retained.
    """

    if not 0.5 <= promotion_threshold <= 1.0:
        raise ValueError("promotion threshold must be in [0.5, 1.0]")

    grouped: dict[str, list[EvidenceClaim]] = {}
    for claim in claims:
        claim.validate()
        grouped.setdefault(claim.key, []).append(claim)

    modeled: dict[str, Any] = {}
    for key in sorted(grouped):
        entries = grouped[key]
        by_value: dict[str, list[EvidenceClaim]] = {}
        for claim in entries:
            by_value.setdefault(_canonical(claim.value), []).append(claim)

        candidates: list[dict[str, Any]] = []
        for canonical_value, same_value in by_value.items():
            strongest_by_kind: dict[str, float] = {}
            for claim in same_value:
                strongest_by_kind[claim.source_kind] = max(
                    strongest_by_kind.get(claim.source_kind, 0.0), float(claim.confidence)
                )
            score = sum(strongest_by_kind.values())
            candidates.append(
                {
                    "canonical_value": canonical_value,
                    "value": json.loads(canonical_value),
                    "score": score,
                    "source_kinds": sorted(strongest_by_kind),
                    "provenance": sorted(
                        [
                            {
                                "source_kind": claim.source_kind,
                                "source_id": claim.source_id,
                                "confidence": float(claim.confidence),
                            }
                            for claim in same_value
                        ],
                        key=lambda item: (item["source_kind"], item["source_id"]),
                    ),
                }
            )

        candidates.sort(
            key=lambda item: (-item["score"], item["canonical_value"])
        )
        total_score = sum(item["score"] for item in candidates)
        winner = candidates[0]
        confidence = winner["score"] / total_score if total_score else 0.0
        verified = (
            confidence >= promotion_threshold
            and len(winner["source_kinds"]) >= 2
        )

        modeled[key] = {
            "value": winner["value"] if verified else None,
            "candidate_value": winner["value"],
            "confidence": confidence,
            "state": "verified" if verified else "uncertain",
            "supporting_source_kinds": winner["source_kinds"],
            "provenance": winner["provenance"],
            "contradictions": [
                {
                    "value": item["value"],
                    "score": item["score"],
                    "source_kinds": item["source_kinds"],
                    "provenance": item["provenance"],
                }
                for item in candidates[1:]
            ],
        }

    model = {
        "schema": MODEL_SCHEMA,
        "actuating": False,
        "claims": modeled,
        "safety": {
            "hardware_access": False,
            "physical_writes_authorized": False,
            "firmware_changes_authorized": False,
            "persistent_device_state_changes_authorized": False,
        },
    }
    model["model_identity"] = _identity(model)
    return model


def synthesize_candidate_interface(model: dict[str, Any]) -> dict[str, Any]:
    """Emit a non-executable candidate interface manifest from verified claims."""

    if model.get("schema") != MODEL_SCHEMA:
        raise ValueError("hardware model schema mismatch")
    claims = model.get("claims")
    if not isinstance(claims, dict):
        raise ValueError("hardware model claims are missing")

    resolved = {
        key: entry["value"]
        for key, entry in sorted(claims.items())
        if isinstance(entry, dict) and entry.get("state") == "verified"
    }
    teacher_sources = sorted(
        {
            provenance["source_id"]
            for entry in claims.values()
            if isinstance(entry, dict)
            for provenance in entry.get("provenance", [])
            if provenance.get("source_kind") == "reference_driver"
        }
    )
    candidate = {
        "schema": CANDIDATE_SCHEMA,
        "model_identity": model.get("model_identity"),
        "mode": "non-actuating",
        "resolved_claims": resolved,
        "reference_driver_teachers": teacher_sources,
        "required_validation": [
            "compare-against-reference-behavior",
            "emulate-state-transitions",
            "preserve-contradictions-and-provenance",
        ],
        "promotion_gates": {
            "physical_write_authorized": False,
            "firmware_change_authorized": False,
            "recovery_path_required_before_physical_actuation": True,
        },
    }
    candidate["candidate_identity"] = _identity(candidate)
    return candidate
