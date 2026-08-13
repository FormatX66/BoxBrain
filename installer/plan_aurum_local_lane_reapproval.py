from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

EXPECTED_DRIFT_KEYS = {
    "deployer_sha256",
    "codelation_tree_sha256",
    "watcher_sha256",
}


def plan_reapproval(
    inspection: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    if int(inspection.get("schema_version", 0)) != 1:
        raise ValueError("Aurum approval inspection schema is unsupported.")
    if int(evidence.get("schema_version", 0)) != 1:
        raise ValueError("Aurum approval evidence schema is unsupported.")

    drift = sorted({str(item) for item in inspection.get("drift", [])})
    unknown = sorted(set(drift) - EXPECTED_DRIFT_KEYS)
    current_commit = str(evidence.get("current_commit", "")).strip()
    tested_commit = str(evidence.get("tested_commit", "")).strip()
    tests_passed = evidence.get("tests_passed") is True

    reasons: list[str] = []
    if unknown:
        reasons.append("unknown-drift-component")
    if "deployer_sha256" in drift:
        reasons.append("deployer-drift-requires-review")
    if "watcher_sha256" in drift:
        reasons.append("watcher-drift-requires-review")
    if not current_commit:
        reasons.append("current-commit-missing")
    if not tested_commit:
        reasons.append("tested-commit-missing")
    if current_commit and tested_commit and current_commit != tested_commit:
        reasons.append("tested-commit-does-not-match-current")
    if not tests_passed:
        reasons.append("tests-not-confirmed-passing")

    approval_current = bool(inspection.get("approval_current")) and not drift
    if approval_current:
        decision = "already-approved"
        reasons = ["approval-current"]
    elif not reasons and drift == ["codelation_tree_sha256"]:
        decision = "refresh-eligible"
        reasons = ["codelation-only-drift", "matching-tested-commit"]
    else:
        decision = "review-required"
        if not drift:
            reasons.append("inspection-inconsistent-or-approval-not-current")

    return {
        "schema_version": 1,
        "decision": decision,
        "drift": drift,
        "reason_codes": sorted(set(reasons)),
        "evidence": {
            "current_commit": current_commit,
            "tested_commit": tested_commit,
            "tests_passed": tests_passed,
        },
        "apply": False,
        "authorization_mutated": False,
        "deployment_performed": False,
        "read_only": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only deterministic Aurum local-lane reapproval planner."
    )
    parser.add_argument("--inspection", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        inspection = json.loads(args.inspection.read_text(encoding="utf-8"))
        evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
        result = plan_reapproval(inspection, evidence)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1

    print(json.dumps({"ok": True, **result}, indent=2, sort_keys=True))
    return 0 if result["decision"] in {"already-approved", "refresh-eligible"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
