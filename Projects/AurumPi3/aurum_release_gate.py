#!/usr/bin/env python3
"""Shared validation for Aurum's same-commit virtual-lab release proof."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable


EVIDENCE_SCHEMA = "aurum-verification-evidence-v1"
CONVERGENCE_SCHEMA = "aurum-convergence-proof-v1"
FULL_COMMIT = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_EVIDENCE: dict[str, tuple[str, str]] = {
    "docker-x86_64": ("container-runtime", "not-implied"),
    "docker-arm64": ("container-runtime", "not-implied"),
    "qemu-x86_64-uefi": ("virtual-machine-uefi-runtime", "not-implied"),
    "qemu-pi3-machine-runtime": ("virtual-machine-runtime", "not-implied"),
}


class GateValidationError(ValueError):
    """Raised when release evidence cannot prove the required convergence."""


def canonical_sha256(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_commit(value: str) -> str:
    commit = value.strip().lower()
    if not FULL_COMMIT.fullmatch(commit):
        raise GateValidationError("commit must be a full 40-character lowercase Git SHA")
    return commit


def evidence_document(target: str, commit: str) -> dict[str, str]:
    normalized_commit = normalize_commit(commit)
    try:
        evidence, physical = REQUIRED_EVIDENCE[target]
    except KeyError as exc:
        raise GateValidationError(f"unsupported verification target: {target}") from exc
    return {
        "schema": EVIDENCE_SCHEMA,
        "commit": normalized_commit,
        "target": target,
        "status": "verified",
        "evidence": evidence,
        "physical_hardware_evidence": physical,
    }


def _validate_evidence(value: dict[str, Any], expected_commit: str) -> dict[str, str]:
    expected_keys = {
        "schema",
        "commit",
        "target",
        "status",
        "evidence",
        "physical_hardware_evidence",
    }
    if set(value) != expected_keys:
        raise GateValidationError("verification evidence contains missing or unexpected fields")
    if value.get("schema") != EVIDENCE_SCHEMA:
        raise GateValidationError("unsupported verification evidence schema")
    target = str(value.get("target", ""))
    if target not in REQUIRED_EVIDENCE:
        raise GateValidationError(f"unexpected verification target: {target!r}")
    if normalize_commit(str(value.get("commit", ""))) != expected_commit:
        raise GateValidationError(f"verification target {target} is from a different commit")
    if value.get("status") != "verified":
        raise GateValidationError(f"verification target {target} did not pass")
    expected_evidence, expected_physical = REQUIRED_EVIDENCE[target]
    if value.get("evidence") != expected_evidence:
        raise GateValidationError(f"verification target {target} has an inaccurate evidence label")
    if value.get("physical_hardware_evidence") != expected_physical:
        raise GateValidationError(
            f"verification target {target} must not claim physical hardware proof"
        )
    return evidence_document(target, expected_commit)


def converge_evidence(
    documents: Iterable[dict[str, Any]], expected_commit: str
) -> dict[str, Any]:
    commit = normalize_commit(expected_commit)
    verified: dict[str, dict[str, str]] = {}
    for document in documents:
        if not isinstance(document, dict):
            raise GateValidationError("verification evidence must be a JSON object")
        normalized = _validate_evidence(document, commit)
        target = normalized["target"]
        if target in verified:
            raise GateValidationError(f"duplicate verification target: {target}")
        verified[target] = {
            "status": normalized["status"],
            "evidence": normalized["evidence"],
            "physical_hardware_evidence": normalized["physical_hardware_evidence"],
        }
    missing = sorted(set(REQUIRED_EVIDENCE) - set(verified))
    if missing:
        raise GateValidationError(f"missing verification targets: {', '.join(missing)}")
    return {
        "schema": CONVERGENCE_SCHEMA,
        "commit": commit,
        "status": "verified",
        "required_targets": {name: verified[name] for name in REQUIRED_EVIDENCE},
        "evidence_labels": {
            "qemu_pi3": "virtual-machine-runtime-proof",
            "physical_hardware": "not-proven-or-implied",
        },
    }


def validate_convergence_proof(
    value: dict[str, Any], expected_commit: str | None = None
) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema") != CONVERGENCE_SCHEMA:
        raise GateValidationError("unsupported convergence proof schema")
    expected_keys = {
        "schema",
        "commit",
        "status",
        "required_targets",
        "evidence_labels",
    }
    if set(value) != expected_keys:
        raise GateValidationError("convergence proof contains missing or unexpected fields")
    commit = normalize_commit(str(value.get("commit", "")))
    if expected_commit is not None and commit != normalize_commit(expected_commit):
        raise GateValidationError("convergence proof is from a different commit")
    if value.get("status") != "verified":
        raise GateValidationError("convergence proof is not verified")
    targets = value.get("required_targets")
    if not isinstance(targets, dict) or set(targets) != set(REQUIRED_EVIDENCE):
        raise GateValidationError("convergence proof does not contain exactly the four required targets")
    documents = []
    for target, details in targets.items():
        if not isinstance(details, dict):
            raise GateValidationError(f"convergence target {target} is invalid")
        if set(details) != {"status", "evidence", "physical_hardware_evidence"}:
            raise GateValidationError(f"convergence target {target} has unexpected fields")
        documents.append(
            {
                "schema": EVIDENCE_SCHEMA,
                "commit": commit,
                "target": target,
                **details,
            }
        )
    normalized = converge_evidence(documents, commit)
    if value.get("evidence_labels") != normalized["evidence_labels"]:
        raise GateValidationError("convergence proof evidence labels are inaccurate")
    return normalized


def validate_update_manifest_gate(manifest: dict[str, Any]) -> dict[str, Any]:
    source_commit = normalize_commit(str(manifest.get("source_commit", "")))
    verification = manifest.get("verification")
    if not isinstance(verification, dict):
        raise GateValidationError("update manifest is missing convergence verification")
    proof = verification.get("convergence")
    if not isinstance(proof, dict):
        raise GateValidationError("update manifest is missing the convergence proof")
    normalized = validate_convergence_proof(proof, source_commit)
    expected_digest = canonical_sha256(normalized)
    if verification.get("convergence_sha256") != expected_digest:
        raise GateValidationError("update manifest convergence proof digest is invalid")
    return normalized
