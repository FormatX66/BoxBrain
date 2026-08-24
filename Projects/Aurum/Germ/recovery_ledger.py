#!/usr/bin/env python3
"""Atomic pre-change checkpoints and a hash-chained Guardian change journal."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

CHECKPOINT_SCHEMA = "aurum-guardian-checkpoint-v1"
JOURNAL_SCHEMA = "aurum-guardian-journal-entry-v1"
HEAD_SCHEMA = "aurum-guardian-journal-head-v1"
SAFE_NAME = re.compile(r"[^a-z0-9-]+")


class LedgerError(RuntimeError):
    pass


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise LedgerError(f"recovery ledger write failed: {exc}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise LedgerError(f"checkpoint digest failed: {exc}") from exc
    return digest.hexdigest()


def _safe_name(change: str) -> str:
    value = SAFE_NAME.sub("-", str(change or "change").lower()).strip("-")
    return (value or "change")[:64]


def _state_view(state: dict[str, Any] | None) -> dict[str, Any] | None:
    if state is None:
        return None
    keys = (
        "schema",
        "active",
        "lkg",
        "lkg_commit",
        "lkg_genetics_commit",
        "lkg_manifest_identity",
        "previous_lkg",
        "previous_lkg_commit",
        "previous_lkg_genetics_commit",
        "previous_lkg_manifest_identity",
        "trial",
        "trial_commit",
        "trial_genetics_commit",
        "trial_manifest_identity",
        "trial_boots",
        "last_result",
        "updated_at_unix",
    )
    return {key: state.get(key) for key in keys if key in state}


def create_checkpoint(
    *,
    state_root: Path,
    slots_root: Path,
    active_link: Path,
    change: str,
    state: dict[str, Any],
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stamp = time.time_ns()
    checkpoint_id = f"{stamp}-{os.getpid()}-{_safe_name(change)}"
    root = state_root / "checkpoints"
    path = root / f"{checkpoint_id}.json"
    try:
        active_target = os.readlink(active_link)
    except OSError:
        active_target = None
    slots: dict[str, Any] = {}
    for slot in ("A", "B"):
        runtime = slots_root / slot / "opt/aurum"
        roles = [role for role in ("active", "lkg", "trial") if state.get(role) == slot]
        slots[slot] = {
            "runtime": str(runtime),
            "runtime_present": runtime.is_dir(),
            "roles": roles,
            "recoverable": runtime.is_dir() and "lkg" in roles,
        }
    payload = {
        "schema": CHECKPOINT_SCHEMA,
        "checkpoint_id": checkpoint_id,
        "change": _safe_name(change),
        "created_at_unix": int(time.time()),
        "created_at_ns": stamp,
        "state": _state_view(state),
        "active_link": {"path": str(active_link), "target": active_target},
        "slots": slots,
        "lkg_preserved": bool(slots.get(str(state.get("lkg")), {}).get("runtime_present")),
        "detail": detail or {},
    }
    _atomic_json(path, payload)
    return {
        "schema": CHECKPOINT_SCHEMA,
        "checkpoint_id": checkpoint_id,
        "path": str(path),
        "sha256": _sha256(path),
    }


def _journal_head(state_root: Path) -> dict[str, Any]:
    path = state_root / "journal-head.json"
    if not path.is_file():
        return {"schema": HEAD_SCHEMA, "record_sha256": None, "record": None}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LedgerError(f"recovery journal head unreadable: {exc}") from exc
    if value.get("schema") != HEAD_SCHEMA:
        raise LedgerError("unsupported recovery journal head")
    digest = value.get("record_sha256")
    if digest is not None and (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
        raise LedgerError("recovery journal head digest is invalid")
    record_value = value.get("record")
    if digest is None:
        if record_value is not None:
            raise LedgerError("empty recovery journal head names a record")
        return value
    if not isinstance(record_value, str):
        raise LedgerError("recovery journal head record is invalid")
    try:
        journal_root = (state_root / "journal").resolve()
        record_path = Path(record_value).resolve(strict=True)
        record_path.relative_to(journal_root)
        record_payload = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise LedgerError(f"recovery journal head record unreadable: {exc}") from exc
    recorded_digest = record_payload.pop("record_sha256", None)
    actual_digest = hashlib.sha256(canonical_json(record_payload)).hexdigest()
    if recorded_digest != digest or actual_digest != digest:
        raise LedgerError("recovery journal head record failed integrity validation")
    return value


def record(
    *,
    state_root: Path,
    change: str,
    phase: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    checkpoint: dict[str, Any] | None,
    requested: dict[str, Any] | None,
    validation: dict[str, Any] | None,
    outcome: str,
) -> dict[str, Any]:
    if phase not in {"prepared", "committed"}:
        raise LedgerError("journal phase must be prepared or committed")
    head = _journal_head(state_root)
    stamp = time.time_ns()
    entry_id = f"{stamp}-{os.getpid()}-{_safe_name(change)}-{phase}"
    payload = {
        "schema": JOURNAL_SCHEMA,
        "entry_id": entry_id,
        "change": _safe_name(change),
        "phase": phase,
        "recorded_at_unix": int(time.time()),
        "recorded_at_ns": stamp,
        "previous_record_sha256": head.get("record_sha256"),
        "before": _state_view(before),
        "after": _state_view(after),
        "requested": requested or {},
        "validation": validation or {},
        "outcome": str(outcome or "unknown")[:128],
        "checkpoint": checkpoint,
    }
    digest = hashlib.sha256(canonical_json(payload)).hexdigest()
    payload["record_sha256"] = digest
    path = state_root / "journal" / f"{entry_id}.json"
    _atomic_json(path, payload)
    _atomic_json(
        state_root / "journal-head.json",
        {
            "schema": HEAD_SCHEMA,
            "record": str(path),
            "record_sha256": digest,
            "updated_at_unix": int(time.time()),
        },
    )
    return {"entry_id": entry_id, "path": str(path), "record_sha256": digest}


def prepare_change(
    *,
    state_root: Path,
    slots_root: Path,
    active_link: Path,
    change: str,
    state: dict[str, Any],
    requested: dict[str, Any] | None = None,
) -> dict[str, Any]:
    checkpoint = create_checkpoint(
        state_root=state_root,
        slots_root=slots_root,
        active_link=active_link,
        change=change,
        state=state,
        detail=requested,
    )
    prepared = record(
        state_root=state_root,
        change=change,
        phase="prepared",
        before=state,
        after=None,
        checkpoint=checkpoint,
        requested=requested,
        validation={"status": "pending"},
        outcome="pending",
    )
    return {"checkpoint": checkpoint, "prepared": prepared}


def commit_change(
    *,
    state_root: Path,
    change: str,
    before: dict[str, Any] | None,
    after: dict[str, Any],
    prepared: dict[str, Any] | None,
    requested: dict[str, Any] | None,
    validation: dict[str, Any] | None,
    outcome: str,
) -> dict[str, Any]:
    return record(
        state_root=state_root,
        change=change,
        phase="committed",
        before=before,
        after=after,
        checkpoint=(prepared or {}).get("checkpoint"),
        requested=requested,
        validation=validation,
        outcome=outcome,
    )
