#!/usr/bin/env python3
"""Aurum protected reseed germ, protocol v1.

This module intentionally does not overwrite or activate the running Aurum
phenotype. Its job is to resolve trusted genetics to an immutable commit and
stage a verified candidate beside the current organism. Candidate growth,
health validation, and promotion are separate guarded phases.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence

SCHEMA = "aurum-genetics-v1"
GERM_PROTOCOL = 1
REPOSITORY = "https://github.com/FormatX66/BoxBrain.git"
DEFAULT_REF = "main"
DEFAULT_STATE_ROOT = Path("/var/lib/aurum/germ")
MANIFEST_RELATIVE = Path("Projects/Aurum/Germ/GENETICS.json")
SAFE_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}")


class GermError(RuntimeError):
    pass


def _run(args: Sequence[str], *, cwd: Path | None = None, timeout: int = 300) -> str:
    try:
        result = subprocess.run(
            list(args),
            cwd=str(cwd) if cwd else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GermError(f"command failed to start: {exc}") from exc
    if result.returncode != 0:
        raise GermError((result.stdout or "command failed").strip()[-2000:])
    return result.stdout.strip()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def validate_ref(ref: str) -> str:
    if not SAFE_REF.fullmatch(ref) or ".." in ref or "//" in ref or ref.endswith(("/", ".lock")):
        raise GermError("requested genetics ref is invalid")
    return ref


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GermError(f"genetics manifest unreadable: {exc}") from exc
    if payload.get("schema") != SCHEMA:
        raise GermError(f"unsupported genetics schema: {payload.get('schema')!r}")
    protocol = payload.get("germ_protocol")
    if not isinstance(protocol, int) or protocol < 1 or protocol > GERM_PROTOCOL:
        raise GermError(
            f"genetics require germ protocol {protocol!r}; this germ supports {GERM_PROTOCOL}"
        )
    if payload.get("repository") != REPOSITORY:
        raise GermError("genetics repository is outside the Aurum allowlist")
    policy = payload.get("policy") or {}
    if policy.get("candidate_only_staging") is not True:
        raise GermError("genetics do not require candidate-only staging")
    if policy.get("live_overwrite_allowed") is not False:
        raise GermError("genetics do not explicitly prohibit live overwrite")
    if policy.get("promotion_requires_health_evidence") is not True:
        raise GermError("genetics do not require health evidence before promotion")
    required = payload.get("required_paths")
    if not isinstance(required, list) or not required or not all(isinstance(item, str) and item for item in required):
        raise GermError("genetics required_paths are missing or invalid")
    return payload


def verify_candidate(candidate: Path) -> dict[str, Any]:
    manifest_path = candidate / MANIFEST_RELATIVE
    manifest = load_manifest(manifest_path)
    missing = [str(p) for p in manifest["required_paths"] if not (candidate / p).exists()]
    if missing:
        raise GermError("candidate genetics are incomplete: " + ", ".join(missing))
    head = _run(["git", "rev-parse", "HEAD"], cwd=candidate)
    if len(head) != 40 or any(c not in "0123456789abcdef" for c in head.lower()):
        raise GermError("candidate did not resolve to an immutable commit SHA")
    return {"commit": head, "manifest": manifest}


def stage(*, ref: str, state_root: Path, authorize_network: bool) -> dict[str, Any]:
    if not authorize_network:
        raise GermError("network genetics access requires --authorize-network")
    ref = validate_ref(ref)
    state_root.mkdir(parents=True, exist_ok=True)
    candidates = state_root / "candidates"
    receipts = state_root / "receipts"
    candidates.mkdir(parents=True, exist_ok=True)
    receipts.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="aurum-germ-", dir=str(state_root)) as temporary:
        work = Path(temporary) / "candidate"
        _run(["git", "init", "-q", str(work)])
        _run(["git", "remote", "add", "origin", REPOSITORY], cwd=work)
        _run(["git", "fetch", "--depth", "1", "origin", ref], cwd=work)
        _run(["git", "checkout", "-q", "--detach", "FETCH_HEAD"], cwd=work)
        verified = verify_candidate(work)
        commit = verified["commit"]
        destination = candidates / commit
        if destination.exists():
            shutil.rmtree(destination)
        os.replace(work, destination)

    receipt = {
        "schema": "aurum-reseed-stage-receipt-v1",
        "status": "staged",
        "repository": REPOSITORY,
        "requested_ref": ref,
        "resolved_commit": commit,
        "candidate": str(destination),
        "active_overwritten": False,
        "promotion_performed": False,
        "health_evidence_required_before_promotion": True,
        "staged_at_unix": int(time.time()),
    }
    _atomic_json(receipts / f"{commit}.json", receipt)
    _atomic_json(state_root / "latest-stage.json", receipt)
    return receipt


def status(state_root: Path) -> dict[str, Any]:
    latest = state_root / "latest-stage.json"
    payload: dict[str, Any] = {
        "schema": "aurum-reseed-germ-status-v1",
        "germ_protocol": GERM_PROTOCOL,
        "repository": REPOSITORY,
        "default_ref": DEFAULT_REF,
        "candidate_only": True,
        "live_overwrite_allowed": False,
        "state_root": str(state_root),
        "latest_stage": None,
    }
    if latest.is_file():
        try:
            payload["latest_stage"] = json.loads(latest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload["latest_stage"] = {"status": "unreadable"}
    return payload


def plan(ref: str, state_root: Path) -> dict[str, Any]:
    ref = validate_ref(ref)
    return {
        "schema": "aurum-reseed-plan-v1",
        "requested_ref": ref,
        "repository": REPOSITORY,
        "state_root": str(state_root),
        "flow": [
            "resolve-trusted-genetics",
            "stage-candidate-beside-active-organism",
            "verify-manifest-and-immutable-commit",
            "hardware-specific-growth",
            "health-gate",
            "promote-only-if-proven",
        ],
        "this_tool_performs": ["resolve-trusted-genetics", "stage-candidate-beside-active-organism", "verify-manifest-and-immutable-commit"],
        "this_tool_does_not_perform": ["live-overwrite", "candidate-promotion", "rollback-of-current-organism"],
    }


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Aurum protected reseed germ")
    p.add_argument("command", choices=("status", "plan", "stage"))
    p.add_argument("--ref", default=DEFAULT_REF)
    p.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    p.add_argument("--authorize-network", action="store_true")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "status":
            result = status(args.state_root)
        elif args.command == "plan":
            result = plan(args.ref, args.state_root)
        else:
            result = stage(
                ref=args.ref,
                state_root=args.state_root,
                authorize_network=args.authorize_network,
            )
    except GermError as exc:
        print(json.dumps({"status": "refused", "detail": str(exc)}, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
