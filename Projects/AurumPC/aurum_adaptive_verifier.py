#!/usr/bin/env python3
"""Aurum adaptive evidence verifier.

Traditional CI asks whether the same source/environment produced the same
artifact. Aurum also needs a verifier for adaptive behavior, where different
capability paths may be valid if they reach the required state while preserving
human-approved boundaries and machine invariants.

This module does not execute work. It verifies receipts and generation evidence.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

VERIFIER_SCHEMA = "aurum.adaptive-verifier.v1"
CONTRACT_SCHEMA = "aurum.adaptive-verification-contract.v1"
PASS = "PASS"
FAIL = "FAIL"


def default_contract() -> dict[str, Any]:
    return {
        "schema": CONTRACT_SCHEMA,
        "allow_path_variation": True,
        "allow_implementation_variation": True,
        "require_desired_state_reached": True,
        "require_execution_authorized": True,
        "require_autonomy_envelope_preserved": True,
        "require_proof": True,
        "require_monotonic_timing": False,
        "protected_invariants": [
            "authorization-preserved",
            "no-destructive-boundary-crossing",
            "trust-boundary-preserved",
        ],
        "principle": "adaptive behavior must be bounded and provable, not identical",
    }


def _bool(receipt: dict[str, Any], key: str) -> bool:
    return bool(receipt.get(key))


def _timing_is_monotonic(timing: dict[str, Any]) -> tuple[bool, str | None]:
    ordered = ["t0", "t1", "t2", "t3", "t4", "t5"]
    values: list[float] = []
    present: list[str] = []
    for key in ordered:
        value = timing.get(key)
        if value is None:
            continue
        if not isinstance(value, (int, float)):
            return False, f"timing-{key}-not-numeric"
        values.append(float(value))
        present.append(key)
    if len(values) < 2:
        return True, None
    for prior, current in zip(values, values[1:]):
        if current < prior:
            return False, f"timing-not-monotonic:{','.join(present)}"
    return True, None


def verify_receipt(
    receipt: dict[str, Any], contract: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Verify one adaptive execution receipt against invariant-based evidence."""
    contract = contract or default_contract()
    failures: list[str] = []
    passes: list[str] = []

    if contract.get("require_desired_state_reached", True):
        if _bool(receipt, "desired_state_reached"):
            passes.append("desired-state-reached")
        else:
            failures.append("desired-state-not-proven")

    if contract.get("require_execution_authorized", True):
        if _bool(receipt, "execution_authorized"):
            passes.append("execution-authorized")
        else:
            failures.append("execution-not-authorized")

    if contract.get("require_autonomy_envelope_preserved", True):
        if _bool(receipt, "autonomy_envelope_preserved"):
            passes.append("autonomy-envelope-preserved")
        else:
            failures.append("autonomy-envelope-not-proven")

    if contract.get("require_proof", True):
        proof = receipt.get("proof")
        if isinstance(proof, dict) and proof:
            passes.append("proof-present")
        else:
            failures.append("proof-missing")

    observed_invariants = set(str(value) for value in receipt.get("invariants_preserved") or [])
    for invariant in contract.get("protected_invariants") or []:
        invariant = str(invariant)
        if invariant in observed_invariants:
            passes.append(f"invariant:{invariant}")
        else:
            failures.append(f"invariant-missing:{invariant}")

    if receipt.get("boundary_crossed"):
        failures.append("reported-boundary-crossing")

    if receipt.get("destructive_effect"):
        failures.append("reported-destructive-effect")

    if contract.get("require_monotonic_timing"):
        ok, reason = _timing_is_monotonic(receipt.get("timing") or {})
        if ok:
            passes.append("timing-monotonic")
        else:
            failures.append(reason or "timing-invalid")

    path = receipt.get("path")
    if path is not None:
        passes.append("path-observed")
    if contract.get("allow_path_variation", True):
        passes.append("path-variation-allowed")
    if contract.get("allow_implementation_variation", True):
        passes.append("implementation-variation-allowed")

    return {
        "schema": VERIFIER_SCHEMA,
        "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "result": PASS if not failures else FAIL,
        "failures": failures,
        "passes": passes,
        "path": path,
        "implementation": receipt.get("implementation"),
        "principle": "verify required state and preserved invariants; do not require identical adaptive path",
    }


def verify_generation(
    candidate: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify a candidate generation and optionally compare it with a baseline.

    Improvement is useful evidence, but lack of improvement is not automatically a
    failure unless the candidate loses a required invariant or desired capability.
    """
    verification = verify_receipt(candidate, contract)
    comparison: dict[str, Any] = {
        "baseline_present": bool(baseline),
        "candidate_score": candidate.get("fitness_score"),
        "baseline_score": baseline.get("fitness_score") if baseline else None,
        "fitness_relation": "unknown",
    }
    if baseline:
        candidate_score = candidate.get("fitness_score")
        baseline_score = baseline.get("fitness_score")
        if isinstance(candidate_score, (int, float)) and isinstance(baseline_score, (int, float)):
            if candidate_score > baseline_score:
                comparison["fitness_relation"] = "improved"
            elif candidate_score == baseline_score:
                comparison["fitness_relation"] = "preserved"
            else:
                comparison["fitness_relation"] = "regressed"
    verification["comparison"] = comparison
    return verification


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Aurum adaptive evidence")
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()

    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    contract = (
        json.loads(args.contract.read_text(encoding="utf-8")) if args.contract else default_contract()
    )
    baseline = json.loads(args.baseline.read_text(encoding="utf-8")) if args.baseline else None
    result = verify_generation(receipt, baseline, contract)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == PASS else 2


if __name__ == "__main__":
    raise SystemExit(main())
