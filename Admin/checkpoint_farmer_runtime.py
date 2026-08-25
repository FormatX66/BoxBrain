#!/usr/bin/env python3
"""Project Aurum Farmer's authoritative ledger into the generic runtime checkpoint.

Farmer's sealed SQLite WAL ledger is the production local operational-state
authority on nodes where Farmer is deployed. This tool does not create a second
runtime truth store. It exports a bounded, zero-authority compatibility snapshot
from Farmer into ``aurum-runtime-checkpoint-v1`` so restart/reconstruction tools
that understand the generic checkpoint can consume Farmer state safely.

The projection refuses to run if the Farmer ledger or signing key is missing or
if the append-only event chain fails verification. It never imports destructive
authority, candidate-promotion permission, or LKG mutation permission from the
ledger into the generic checkpoint.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from Admin.checkpoint_aurum_runtime import DEFAULT_OUTPUT, ROOT, CheckpointError, checkpoint
except ModuleNotFoundError:  # Support direct execution from Admin/.
    from checkpoint_aurum_runtime import DEFAULT_OUTPUT, ROOT, CheckpointError, checkpoint


class FarmerProjectionError(ValueError):
    """Farmer state cannot be safely projected into a compatibility checkpoint."""


STATE_MAP = {
    "RECEIVED": "runnable",
    "PLANNED": "runnable",
    "READY": "runnable",
    "RUNNING": "running",
    "VERIFYING": "running",
    "RETRYING": "retrying",
    "RECOVERING": "retrying",
    "WAITING": "blocked",
    "BLOCKED_HUMAN": "blocked",
    "SUCCEEDED": "completed",
    "FAILED_FINAL": "failed",
    "CANCELLED": "completed",
}


def _load_ledger(root: Path, ledger_path: Path, signing_key_path: Path | None):
    ledger_path = ledger_path.expanduser().resolve()
    key_path = (signing_key_path or ledger_path.with_suffix(".key")).expanduser().resolve()
    if not ledger_path.is_file():
        raise FarmerProjectionError(f"Farmer ledger missing: {ledger_path}")
    if not key_path.is_file():
        raise FarmerProjectionError(f"Farmer signing key missing: {key_path}")

    farmer_root = root.resolve() / "Projects/AurumFarmer"
    if not farmer_root.is_dir():
        raise FarmerProjectionError(f"Farmer package missing: {farmer_root}")
    sys.path.insert(0, str(farmer_root))
    try:
        from aurum_farmer.ledger import Ledger, LedgerError
    except ImportError as exc:  # pragma: no cover - defensive direct-execution path
        raise FarmerProjectionError(f"cannot import Aurum Farmer runtime: {exc}") from exc

    try:
        ledger = Ledger(ledger_path, signing_key_path=key_path)
    except LedgerError as exc:
        raise FarmerProjectionError(f"Farmer ledger refused: {exc}") from exc
    if not ledger.verify_event_chain():
        raise FarmerProjectionError("Farmer event chain verification failed")
    return ledger, ledger_path, key_path


def build_farmer_overlay(ledger, *, ledger_path: Path, signing_key_path: Path) -> dict[str, Any]:
    """Create a zero-authority generic runtime overlay from Farmer state."""
    stats = ledger.stats()
    jobs: list[dict[str, Any]] = []
    for raw in ledger.list_jobs(limit=10000):
        farmer_state = str(raw["state"])
        generic_state = STATE_MAP.get(farmer_state)
        if generic_state is None:
            raise FarmerProjectionError(f"unsupported Farmer job state: {farmer_state}")
        full = ledger.get_job(str(raw["id"]))
        receipts = [
            item["id"]
            for item in full.get("evidence", [])
            if item.get("kind") == "farmer_receipt" and item.get("seal_valid")
        ]
        jobs.append(
            {
                "id": str(raw["id"]),
                "state": generic_state,
                "depends_on": [],
                "checkpoint": {
                    "source": "aurum-farmer-ledger",
                    "farmer_state": farmer_state,
                    "version": int(raw.get("version", 0)),
                    "updated_at": raw.get("updated_at"),
                    "current_branch_id": raw.get("current_branch_id"),
                    "lease_owner": raw.get("lease_owner"),
                    "lease_expires_at": raw.get("lease_expires_at"),
                },
                "evidence": {
                    "farmer_receipts": receipts,
                    "event_chain_valid": True,
                },
                "resume_hint": raw.get("next_action"),
            }
        )

    return {
        "operational_state_source": "aurum-farmer-ledger",
        "source_metadata": {
            "ledger": str(ledger_path),
            "signing_key_present": signing_key_path.is_file(),
            "schema_version": stats.get("schema_version"),
            "event_chain_valid": bool(stats.get("event_chain_valid")),
            "running_attempts": int(stats.get("running_attempts", 0)),
            "job_state_counts": stats.get("states", {}),
            "projection_semantics": "compatibility-snapshot-not-peer-authority",
        },
        "jobs": jobs,
        "software_fingerprint": {
            "aurum_farmer_schema_version": stats.get("schema_version"),
            "aurum_farmer_event_chain_valid": bool(stats.get("event_chain_valid")),
        },
        "local_artifacts": [
            {
                "kind": "farmer-ledger",
                "path": str(ledger_path),
                "authoritative_for_local_operational_state": True,
            }
        ],
    }


def project_farmer_checkpoint(
    *,
    root: Path = ROOT,
    ledger_path: Path,
    signing_key_path: Path | None = None,
    output: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    ledger, resolved_ledger, resolved_key = _load_ledger(root, ledger_path, signing_key_path)
    overlay = build_farmer_overlay(
        ledger,
        ledger_path=resolved_ledger,
        signing_key_path=resolved_key,
    )
    value = checkpoint(root=root, output=output, overlay=overlay)
    if value["authority"]["authority_granted"]:
        raise FarmerProjectionError("compatibility checkpoint unexpectedly granted authority")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--signing-key", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        value = project_farmer_checkpoint(
            root=args.root,
            ledger_path=args.ledger,
            signing_key_path=args.signing_key,
            output=args.output,
        )
    except (FarmerProjectionError, CheckpointError) as exc:
        raise SystemExit(f"AURUM_FARMER_CHECKPOINT_REFUSED reason={exc}") from exc
    print(
        json.dumps(
            {
                "schema": value["schema"],
                "output": str(args.output),
                "operational_state_source": value["runtime"]["operational_state_source"],
                "jobs": len(value["runtime"]["jobs"]),
                "resumable": len(value["runtime"]["resumable"]),
                "authority_granted": value["authority"]["authority_granted"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
