"""Project durable Tiny Seed fallback evidence into the live Future Branch state.

This projector is deliberately evidence-only. It cannot grant write authority,
promote an experimental carrier, or infer physical compatibility. Its purpose is to
make a warm fallback cool automatically whenever its proof no longer matches the
current canonical Tiny Seed release or the same experimental head.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HANDOFF = Path("Projects/Aurum/Release/latest-tinyseed-handoff.json")
PROVENANCE = Path(
    "Projects/Aurum/Release/critical-workflows/"
    "aurum-tiny-seed-fallback-canonical-provenance.json"
)
MATRIX = Path(
    "Projects/Aurum/Release/critical-workflows/"
    "aurum-tiny-seed-x86-fallback-carrier-matrix-experiment.json"
)
BRANCH = Path("Projects/Aurum/future-branches.json")
CRITICAL_SCHEMA = "aurum-critical-workflow-evidence-v1"


class FallbackEvidenceError(ValueError):
    pass


def _read(path: Path, *, required: bool = True) -> dict:
    if not path.is_file():
        if required:
            raise FallbackEvidenceError(f"missing evidence: {path}")
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FallbackEvidenceError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise FallbackEvidenceError(f"expected object: {path}")
    return value


def _success(receipt: dict) -> bool:
    if not receipt:
        return False
    if receipt.get("schema") != CRITICAL_SCHEMA:
        raise FallbackEvidenceError("unexpected critical workflow evidence schema")
    return receipt.get("status") == "completed" and receipt.get("conclusion") == "success"


def _update_seed_method_pivot(branch: dict, *, current: bool, provenance_current: bool) -> None:
    entries = branch.get("likely_user_inputs")
    if entries is None:
        return
    if not isinstance(entries, list):
        raise FallbackEvidenceError("likely_user_inputs must be an array")
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("input_family") != "seed-method-pivot":
            continue
        if current:
            entry["prepared_response"] = (
                "The x86 fallback carrier has current-release canonical-provenance proof and "
                "successful same-head virtual build/boot proof. Keep it warm as an isolated "
                "experimental fallback; this is not physical HP proof and grants no write authority."
            )
        elif provenance_current:
            entry["prepared_response"] = (
                "The fallback payload is re-proven against the current canonical release, but "
                "same-head fallback build/boot publication is not yet current. Keep the method "
                "prepared but cool until the matrix succeeds on that exact experimental head."
            )
        else:
            entry["prepared_response"] = (
                "The fallback carrier is not currently provenance-locked to the canonical "
                "READY_TO_FLASH release. Treat older virtual success as historical only and "
                "re-prove canonical payload provenance plus same-head build/boot before calling it warm."
            )
        entry["action_if_safe"] = (
            "Compare fresh physical carrier evidence and expected total cost while preserving the "
            "same Germ/genetics/LKG contract. Never promote the experimental carrier from virtual "
            "evidence alone."
        )
        return


def sync_fallback_evidence(root: Path = ROOT) -> dict:
    handoff = _read(root / HANDOFF)
    if handoff.get("schema") != "aurum-tinyseed-handoff-v1":
        raise FallbackEvidenceError("unexpected Tiny Seed handoff schema")
    source = str(handoff.get("source_commit") or "").strip()
    if not source:
        raise FallbackEvidenceError("canonical source commit required")

    provenance = _read(root / PROVENANCE, required=False)
    matrix = _read(root / MATRIX, required=False)
    provenance_success = _success(provenance)
    matrix_success = _success(matrix)

    provenance_head = str(provenance.get("head_sha") or "").strip() or None
    matrix_head = str(matrix.get("head_sha") or "").strip() or None
    provenance_source = str(provenance.get("canonical_release_source_commit") or "").strip() or None
    payload_match = provenance.get("canonical_payload_match") is True
    provenance_current = bool(
        provenance_success
        and payload_match
        and provenance_source == source
        and handoff.get("state") == "READY_TO_FLASH"
    )
    same_head = bool(provenance_head and matrix_head and provenance_head == matrix_head)
    warm_current = bool(provenance_current and matrix_success and same_head)

    fallback = {
        "provenance_receipt_present": bool(provenance),
        "provenance_success": provenance_success,
        "provenance_head_sha": provenance_head,
        "provenance_release_source_commit": provenance_source,
        "provenance_matches_current_release": provenance_current,
        "canonical_payload_match": payload_match,
        "matrix_receipt_present": bool(matrix),
        "matrix_success": matrix_success,
        "matrix_head_sha": matrix_head,
        "same_experimental_head": same_head,
        "warm_current": warm_current,
        "physical_proof_inferred": False,
        "authority_granted": False,
    }

    branch_path = root / BRANCH
    branch = _read(branch_path)
    projected = copy.deepcopy(branch)
    canonical = projected.setdefault("canonical_evidence", {})
    if not isinstance(canonical, dict):
        raise FallbackEvidenceError("canonical_evidence must be an object")
    canonical["fallback_carrier"] = fallback
    live = projected.setdefault("live_controls", {})
    if not isinstance(live, dict):
        raise FallbackEvidenceError("live_controls must be an object")
    live["fallback_carrier_current"] = warm_current
    live["fallback_carrier_provenance_current"] = provenance_current
    _update_seed_method_pivot(projected, current=warm_current, provenance_current=provenance_current)

    changed = projected != branch
    if changed:
        branch_path.write_text(json.dumps(projected, indent=2) + "\n", encoding="utf-8")
    return {
        "changed": changed,
        "canonical_release_source_commit": source,
        "fallback_provenance_current": provenance_current,
        "fallback_same_head": same_head,
        "fallback_warm_current": warm_current,
    }


def main() -> int:
    try:
        result = sync_fallback_evidence()
    except FallbackEvidenceError as exc:
        print(f"AURUM_FALLBACK_EVIDENCE_SYNC_REFUSED reason={exc}", file=sys.stderr)
        return 1
    print(
        "AURUM_FALLBACK_EVIDENCE_SYNC "
        f"changed={str(result['changed']).lower()} "
        f"source={result['canonical_release_source_commit']} "
        f"provenance_current={str(result['fallback_provenance_current']).lower()} "
        f"same_head={str(result['fallback_same_head']).lower()} "
        f"warm_current={str(result['fallback_warm_current']).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
