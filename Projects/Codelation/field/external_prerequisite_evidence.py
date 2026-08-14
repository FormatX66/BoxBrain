from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
import time
from typing import Any, Mapping

from native_gap_catalog import NativeSemanticGap


EVIDENCE_SCHEMA = "aurum-external-prerequisite-evidence-v0"
BBPI4_PRESENCE_KIND = "bbpi4-physical-presence"
BBPI4_PRESENCE_SOURCE = "aurum-public-controller-fresh-node"
WINDOWS_CONTROLLER_NODE_IDS = frozenset({"825e5a7b7d4a7aed", "85404f41d5507372"})
EVIDENCE_PATH = Path(__file__).resolve().parents[1] / "autobuild" / "external_evidence" / "bbpi4_presence.json"
MAX_EVIDENCE_BYTES = 16384
MAX_NODE_AGE_SECONDS = 300
MAX_EVIDENCE_LIFETIME_SECONDS = 1800
MAX_FUTURE_SKEW_SECONDS = 120


@dataclass(frozen=True)
class ExternalEvidenceApplication:
    spec: NativeSemanticGap
    applied: bool
    reason: str
    evidence: Mapping[str, Any] | None = None


def _bounded_text(value: object, maximum: int) -> str:
    text = str(value or "")
    return text if 0 < len(text) <= maximum else ""


def apply_external_prerequisite_evidence(
    spec: NativeSemanticGap,
    evidence: Mapping[str, Any] | None,
    *,
    now: int | None = None,
) -> ExternalEvidenceApplication:
    """Apply only fresh, bounded physical-presence evidence to live-trial readiness.

    This adapter cannot grant user permission, verify input/display carriers, perform
    I/O, or authorize actuation. Its sole allowed mutation is changing the
    readiness classifier's ``physical_node_present`` invocation argument to
    ``yes`` after a fresh non-controller BBPI4 heartbeat has been recorded.
    """
    if spec.name != "adaptive_shell_live_trial_readiness":
        return ExternalEvidenceApplication(spec, False, "gap-not-evidence-bound")
    if "physical_node_present" not in spec.invocation_arguments:
        return ExternalEvidenceApplication(spec, False, "physical-presence-parameter-missing")
    if not isinstance(evidence, Mapping):
        return ExternalEvidenceApplication(spec, False, "evidence-missing")

    if evidence.get("schema") != EVIDENCE_SCHEMA:
        return ExternalEvidenceApplication(spec, False, "evidence-schema-invalid")
    if evidence.get("kind") != BBPI4_PRESENCE_KIND:
        return ExternalEvidenceApplication(spec, False, "evidence-kind-invalid")
    if evidence.get("source") != BBPI4_PRESENCE_SOURCE:
        return ExternalEvidenceApplication(spec, False, "evidence-source-invalid")
    if evidence.get("verified") is not True:
        return ExternalEvidenceApplication(spec, False, "evidence-not-verified")

    node_id = _bounded_text(evidence.get("node_id"), 64)
    node_name = _bounded_text(evidence.get("name"), 128)
    carrier = _bounded_text(evidence.get("carrier"), 64)
    if not node_id or node_id in WINDOWS_CONTROLLER_NODE_IDS:
        return ExternalEvidenceApplication(spec, False, "physical-node-identity-invalid")
    if not node_name or not carrier:
        return ExternalEvidenceApplication(spec, False, "physical-node-description-invalid")

    try:
        last_seen = int(evidence.get("last_seen"))
        observed_at = int(evidence.get("observed_at"))
        expires_at = int(evidence.get("expires_at"))
    except (TypeError, ValueError):
        return ExternalEvidenceApplication(spec, False, "evidence-time-invalid")

    current = int(time.time()) if now is None else int(now)
    if observed_at > current + MAX_FUTURE_SKEW_SECONDS or last_seen > observed_at + MAX_FUTURE_SKEW_SECONDS:
        return ExternalEvidenceApplication(spec, False, "evidence-time-in-future")
    if observed_at - last_seen > MAX_NODE_AGE_SECONDS:
        return ExternalEvidenceApplication(spec, False, "physical-node-heartbeat-stale")
    if expires_at < current:
        return ExternalEvidenceApplication(spec, False, "evidence-expired")
    if expires_at <= observed_at or expires_at - observed_at > MAX_EVIDENCE_LIFETIME_SECONDS:
        return ExternalEvidenceApplication(spec, False, "evidence-lifetime-invalid")

    invocation = dict(spec.invocation_arguments)
    invocation["physical_node_present"] = "yes"
    applied_spec = replace(spec, invocation_arguments=invocation)
    trace = {
        "schema": EVIDENCE_SCHEMA,
        "kind": BBPI4_PRESENCE_KIND,
        "source": BBPI4_PRESENCE_SOURCE,
        "node_id": node_id,
        "name": node_name,
        "carrier": carrier,
        "last_seen": last_seen,
        "observed_at": observed_at,
        "expires_at": expires_at,
        "authority_granted": False,
        "permission_granted": False,
        "input_carrier_verified": False,
        "display_carrier_verified": False,
    }
    return ExternalEvidenceApplication(applied_spec, True, "fresh-physical-node-evidence", trace)


def apply_external_prerequisite_evidence_from_file(
    spec: NativeSemanticGap,
    *,
    path: Path = EVIDENCE_PATH,
    now: int | None = None,
) -> ExternalEvidenceApplication:
    if spec.name != "adaptive_shell_live_trial_readiness":
        return ExternalEvidenceApplication(spec, False, "gap-not-evidence-bound")
    if not path.is_file():
        return ExternalEvidenceApplication(spec, False, "evidence-file-missing")
    if path.stat().st_size > MAX_EVIDENCE_BYTES:
        return ExternalEvidenceApplication(spec, False, "evidence-file-too-large")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ExternalEvidenceApplication(spec, False, "evidence-file-invalid")
    if not isinstance(raw, dict):
        return ExternalEvidenceApplication(spec, False, "evidence-file-not-object")
    return apply_external_prerequisite_evidence(spec, raw, now=now)


__all__ = [
    "BBPI4_PRESENCE_KIND",
    "BBPI4_PRESENCE_SOURCE",
    "EVIDENCE_PATH",
    "EVIDENCE_SCHEMA",
    "ExternalEvidenceApplication",
    "apply_external_prerequisite_evidence",
    "apply_external_prerequisite_evidence_from_file",
]
