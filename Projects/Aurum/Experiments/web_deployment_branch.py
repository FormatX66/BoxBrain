"""Concrete Future Branch adapter for Aurum web/dashboard deployment evidence.

The generic operational planner is intentionally domain-neutral.  This adapter
consumes the real ``web-static-mirror-*.json`` receipts produced by the Aurum
web/voice mirror workflow and turns them into a zero-authority website deployment
field.  It may prepare validation and rollback work, but it never interprets a
working static mirror or missing hosted-deployment configuration as permission to
deploy externally.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from operational_branch import WorkflowCandidate, WorkflowDomain, operational_plan


RECEIPT_SCHEMA = "aurum-web-static-mirror-receipt-v1"
VERIFIED_STATE = "WEB_STATIC_MIRROR_OK"


def _strict_bool(value: Any, *, field: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{field} must be boolean")
    return value


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("observed_at required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def validate_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        raise ValueError("receipt must be an object")
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise ValueError("unsupported web mirror receipt schema")
    state = receipt.get("state")
    if not isinstance(state, str) or not state:
        raise ValueError("state required")
    source_commit = receipt.get("source_commit")
    if not isinstance(source_commit, str) or len(source_commit) < 7:
        raise ValueError("source_commit required")
    observed_at = _parse_time(receipt.get("observed_at"))

    hosted = receipt.get("hosted_deployment")
    if not isinstance(hosted, dict):
        raise ValueError("hosted_deployment required")
    configured = _strict_bool(hosted.get("configured"), field="hosted_deployment.configured")
    missing = hosted.get("missing", [])
    if not isinstance(missing, list) or not all(isinstance(item, str) for item in missing):
        raise ValueError("hosted_deployment.missing must be a string list")

    verified = receipt.get("verified")
    if not isinstance(verified, dict):
        raise ValueError("verified evidence required")
    for key, value in verified.items():
        if key == "seeded_floor":
            if not isinstance(value, str):
                raise ValueError("verified.seeded_floor must be a string")
            continue
        _strict_bool(value, field=f"verified.{key}")

    return {
        "state": state,
        "source_commit": source_commit,
        "observed_at": observed_at,
        "hosted_configured": configured,
        "hosted_missing": list(missing),
        "verified": dict(verified),
    }


def latest_repository_receipt(repo_root: Path) -> tuple[Path, dict[str, Any]]:
    results = repo_root / "Projects" / "AurumBridge" / "results"
    candidates: list[tuple[datetime, Path, dict[str, Any]]] = []
    for path in results.glob("web-static-mirror-*.json"):
        try:
            receipt = json.loads(path.read_text(encoding="utf-8-sig"))
            normalized = validate_receipt(receipt)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        candidates.append((normalized["observed_at"], path, receipt))
    if not candidates:
        raise FileNotFoundError("no valid Aurum web static mirror receipt found")
    _, path, receipt = max(candidates, key=lambda item: (item[0], item[1].name))
    return path, receipt


def web_deployment_plan(receipt: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    normalized = validate_receipt(receipt)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    age_hours = max(0.0, (now.astimezone(timezone.utc) - normalized["observed_at"]).total_seconds() / 3600.0)
    freshness = max(0.05, min(1.0, 1.0 - age_hours / 24.0))
    mirror_verified = normalized["state"] == VERIFIED_STATE

    candidates = [
        WorkflowCandidate(
            name="revalidate-static-dashboard-sources",
            domain=WorkflowDomain.WEBSITE_DEPLOYMENT,
            probability=0.95 if mirror_verified else 0.80,
            impact=0.85,
            human_time_saved=1.5,
            preparation_leverage=1.4,
            cost=0.05,
            evidence_freshness=freshness,
            read_only=True,
            preserves_verified_state=True,
        ),
        WorkflowCandidate(
            name="prepare-web-rollback-and-source-snapshot",
            domain=WorkflowDomain.WEBSITE_DEPLOYMENT,
            probability=0.70,
            impact=0.90,
            human_time_saved=1.0,
            preparation_leverage=1.6,
            cost=0.10,
            evidence_freshness=freshness,
            reversible=True,
            preserves_verified_state=True,
        ),
    ]

    if normalized["hosted_configured"]:
        candidates.extend(
            [
                WorkflowCandidate(
                    name="validate-hosted-dashboard-candidate",
                    domain=WorkflowDomain.WEBSITE_DEPLOYMENT,
                    probability=0.75,
                    impact=0.95,
                    human_time_saved=2.0,
                    preparation_leverage=1.5,
                    cost=0.15,
                    evidence_freshness=freshness,
                    read_only=True,
                    rollback_prepared=True,
                    preserves_verified_state=True,
                ),
                WorkflowCandidate(
                    name="promote-hosted-dashboard",
                    domain=WorkflowDomain.WEBSITE_DEPLOYMENT,
                    probability=0.55,
                    impact=0.95,
                    human_time_saved=1.0,
                    preparation_leverage=1.0,
                    cost=0.30,
                    evidence_freshness=freshness,
                    external_side_effect=True,
                    authorization_required=True,
                    rollback_prepared=True,
                    preserves_verified_state=True,
                ),
            ]
        )
    else:
        candidates.append(
            WorkflowCandidate(
                name="hosted-dashboard-configuration-boundary",
                domain=WorkflowDomain.WEBSITE_DEPLOYMENT,
                probability=0.45,
                impact=0.70,
                human_time_saved=0.5,
                preparation_leverage=0.8,
                cost=0.20,
                evidence_freshness=freshness,
                external_side_effect=True,
                authorization_required=True,
                rollback_prepared=True,
                preserves_verified_state=True,
            )
        )

    plan = operational_plan(
        candidates,
        verified_state=VERIFIED_STATE if mirror_verified else "WEB_STATIC_MIRROR_UNVERIFIED",
    )
    plan.update(
        {
            "schema": "aurum-future-branch-web-deployment-plan-v1",
            "source_receipt_schema": RECEIPT_SCHEMA,
            "source_commit": normalized["source_commit"],
            "source_observed_at": normalized["observed_at"].isoformat(),
            "evidence_freshness": round(freshness, 6),
            "static_mirror_verified": mirror_verified,
            "hosted_deployment_configured": normalized["hosted_configured"],
            "hosted_deployment_missing": normalized["hosted_missing"],
            "external_action_allowed": False,
            "deployment_promotion_allowed": False,
            "authority_granted": False,
        }
    )
    return plan


def current_repository_plan(repo_root: Path, *, now: datetime | None = None) -> dict[str, Any]:
    path, receipt = latest_repository_receipt(repo_root)
    plan = web_deployment_plan(receipt, now=now)
    plan["source_receipt_path"] = path.relative_to(repo_root).as_posix()
    return plan
