#!/usr/bin/env python3
"""Classify whether an Aurum local-lane result belongs to the current task.

This helper is intentionally read-only. It never changes approval, task, result,
or target state. Its primary safety property is that a stale result can never be
accepted as evidence for a newer request.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


def _request_id(record: Mapping[str, Any] | None) -> str:
    if not record:
        return ""
    value = record.get("request_id")
    return str(value).strip() if value is not None else ""


def classify_result(
    task: Mapping[str, Any], result: Mapping[str, Any] | None
) -> dict[str, Any]:
    task_id = _request_id(task)
    if not task_id:
        return {
            "status": "invalid-task",
            "reason": "task-request-id-missing",
            "current_request_id": None,
            "result_request_id": _request_id(result) or None,
            "accept_result": False,
        }

    if not result:
        return {
            "status": "pending",
            "reason": "result-missing",
            "current_request_id": task_id,
            "result_request_id": None,
            "accept_result": False,
        }

    result_id = _request_id(result)
    if result_id != task_id:
        return {
            "status": "pending",
            "reason": "stale-result-request-id-mismatch",
            "current_request_id": task_id,
            "result_request_id": result_id or None,
            "accept_result": False,
        }

    lane_status = str(result.get("status") or "").strip()
    verified = result.get("verified") is True
    if verified:
        status = "verified"
        reason = "matching-verified-result"
    elif lane_status:
        status = "completed-unverified"
        reason = "matching-result-not-verified"
    else:
        status = "completed-unverified"
        reason = "matching-result-status-missing"

    return {
        "status": status,
        "reason": reason,
        "current_request_id": task_id,
        "result_request_id": result_id,
        "lane_status": lane_status or None,
        "verified": verified,
        "accept_result": True,
    }


def _load(path: Path, *, optional: bool = False) -> Mapping[str, Any] | None:
    if optional and not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task", type=Path)
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    outcome = classify_result(
        _load(args.task) or {},
        _load(args.result, optional=True),
    )
    print(json.dumps(outcome, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
