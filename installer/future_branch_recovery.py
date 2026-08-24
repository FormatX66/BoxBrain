"""Build an auditable Future Branch recovery manifest without changing a machine.

This helper is intentionally proposal-only. It describes the candidate, Last Known
Good, rollback, and wait-for-health futures that exist immediately before an Aurum
seed reconciliation. BrainConnect/State Guardian remains the decision authority.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _evidence(ref: str, *, supports: bool, quality: float = 1.0, weight: float = 1.0) -> dict[str, Any]:
    if not ref:
        raise ValueError("evidence ref required")
    for name, value in (("quality", quality), ("weight", weight)):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be between 0 and 1")
    return {
        "ref": ref,
        "supports": bool(supports),
        "quality": float(quality),
        "weight": float(weight),
    }


def recovery_manifest(
    *,
    candidate_state: str,
    lkg_state: str,
    rollback_target: str | None,
    candidate_tests_passed: bool,
    current_seed_present: bool,
    desired_state: str | None = None,
) -> dict[str, Any]:
    """Return the bounded pre-mutation Future Branch field.

    No branch is promoted here. The manifest records what can be considered and
    what evidence exists before mutation so rollback/LKG is a first-class future,
    not merely an exception handler after failure.
    """

    if not candidate_state:
        raise ValueError("candidate_state required")
    if not lkg_state:
        raise ValueError("lkg_state required")

    candidate_evidence = (
        _evidence("candidate.overlay-tests", supports=candidate_tests_passed),
        _evidence("lkg.current-seed-present", supports=current_seed_present),
    )
    if desired_state:
        candidate_evidence += (
            _evidence(f"desired-state:{desired_state}", supports=True, quality=0.8, weight=0.5),
        )

    branches: list[dict[str, Any]] = [
        {
            "branch_id": "seed-candidate",
            "proposed_state": candidate_state,
            "confidence": 0.82 if candidate_tests_passed else 0.20,
            "risk": 0.25,
            "cost": 0.25,
            "reversibility": "full" if rollback_target else "partial",
            "evidence": list(candidate_evidence),
            "status": "warm" if candidate_tests_passed else "quarantined",
            "requires_authorization": True,
            "authorized": False,
            "rollback_target": rollback_target,
            "is_last_known_good": False,
        },
        {
            "branch_id": "seed-lkg",
            "proposed_state": lkg_state,
            "confidence": 0.98 if current_seed_present else 0.40,
            "risk": 0.05,
            "cost": 0.05,
            "reversibility": "full",
            "evidence": [
                _evidence("lkg.current-seed-present", supports=current_seed_present),
            ],
            "status": "verified" if current_seed_present else "warm",
            "requires_authorization": False,
            "authorized": True,
            "rollback_target": None,
            "is_last_known_good": current_seed_present,
        },
        {
            "branch_id": "seed-wait-health",
            "proposed_state": "gather-independent-health-evidence",
            "confidence": 0.72,
            "risk": 0.0,
            "cost": 0.05,
            "reversibility": "full",
            "evidence": [],
            "status": "warm",
            "requires_authorization": False,
            "authorized": True,
            "rollback_target": lkg_state if current_seed_present else None,
            "is_last_known_good": False,
        },
    ]

    if rollback_target:
        branches.append(
            {
                "branch_id": "seed-rollback",
                "proposed_state": lkg_state,
                "confidence": 0.90,
                "risk": 0.05,
                "cost": 0.10,
                "reversibility": "full",
                "evidence": [
                    _evidence("rollback.snapshot-created", supports=True),
                ],
                "status": "warm",
                "requires_authorization": False,
                "authorized": True,
                "rollback_target": rollback_target,
                "is_last_known_good": False,
            }
        )

    return {
        "schema": "aurum-future-branch-recovery-v1",
        "phase": "pre-mutation",
        "decision_authority": "BrainConnect/StateGuardian",
        "promotion_performed": False,
        "desired_state_constraint": desired_state,
        "branches": branches,
        "invariants": {
            "lkg_destroy_allowed": False,
            "candidate_direct_promotion_allowed": False,
            "rollback_must_remain_available": bool(rollback_target),
            "verification_required_after_mutation": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--lkg", required=True)
    parser.add_argument("--rollback")
    parser.add_argument("--candidate-tests-passed", action="store_true")
    parser.add_argument("--current-seed-present", action="store_true")
    parser.add_argument("--desired-state")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    payload = recovery_manifest(
        candidate_state=args.candidate,
        lkg_state=args.lkg,
        rollback_target=args.rollback,
        candidate_tests_passed=args.candidate_tests_passed,
        current_seed_present=args.current_seed_present,
        desired_state=args.desired_state,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
