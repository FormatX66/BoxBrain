#!/usr/bin/env python3
"""Aurum protected reseed germ, protocol v1.

Git is genetics, not a disk-image updater. This germ resolves trusted genetics,
stages immutable source, grows a hardware-family candidate beside the active
organism, verifies it, and arms it as a trial through the independent guardian.
The previous LKG remains intact until the next boot proves the candidate.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence

import bridge

SCHEMA = "aurum-genetics-v1"
GERM_PROTOCOL = 1
REPOSITORY = "https://github.com/FormatX66/BoxBrain.git"
DEFAULT_REF = "main"
DEFAULT_STATE_ROOT = Path("/var/lib/aurum/germ")
SLOTS_ROOT = Path("/var/lib/aurum/slots")
MANIFEST_RELATIVE = Path("Projects/Aurum/Germ/GENETICS.json")
SAFE_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}")


class GermError(RuntimeError):
    pass


def _run(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: int = 300,
    env: dict[str, str] | None = None,
) -> str:
    try:
        result = subprocess.run(
            list(args),
            cwd=str(cwd) if cwd else None,
            env=env,
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
    platforms = payload.get("platforms")
    if not isinstance(platforms, dict) or not platforms:
        raise GermError("genetics platform adapters are missing")
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
    return {"commit": head.lower(), "manifest": manifest}


def _fetch_ref(ref: str, destination: Path) -> str:
    ref = validate_ref(ref)
    _run(["git", "init", "-q", str(destination)])
    _run(["git", "remote", "add", "origin", REPOSITORY], cwd=destination)
    _run(["git", "fetch", "--depth", "1", "origin", ref], cwd=destination, timeout=300)
    _run(["git", "checkout", "-q", "--detach", "FETCH_HEAD"], cwd=destination)
    head = _run(["git", "rev-parse", "HEAD"], cwd=destination)
    if len(head) != 40 or any(c not in "0123456789abcdef" for c in head.lower()):
        raise GermError("fetched source did not resolve to an immutable commit")
    return head.lower()


def stage(*, ref: str, state_root: Path, authorize_network: bool) -> dict[str, Any]:
    if not authorize_network:
        raise GermError("network genetics access requires --authorize-network")
    ref = validate_ref(ref)
    state_root.mkdir(parents=True, exist_ok=True)
    candidates = state_root / "genetics"
    receipts = state_root / "receipts"
    candidates.mkdir(parents=True, exist_ok=True)
    receipts.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="aurum-germ-", dir=str(state_root)) as temporary:
        work = Path(temporary) / "candidate"
        _fetch_ref(ref, work)
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
    _atomic_json(receipts / f"genetics-{commit}.json", receipt)
    _atomic_json(state_root / "latest-stage.json", receipt)
    return receipt


def _architecture() -> str:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return "x86_64"
    if machine in {"aarch64", "arm64"}:
        return "arm64"
    return machine or "unknown"


def _load_slot_state(state_root: Path) -> dict[str, Any]:
    path = state_root / "slots.json"
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GermError(f"A/B slot state is unavailable: {exc}; install the germ bridge first") from exc
    if state.get("active") not in {"A", "B"} or state.get("lkg") not in {"A", "B"}:
        raise GermError("A/B slot state is invalid")
    if state.get("trial"):
        raise GermError("a candidate trial is already pending; prove or roll it back before regrowing again")
    return state


def _copy_runtime(source: Path, adapter: dict[str, Any], runtime: Path) -> None:
    runtime_root = source / str(adapter.get("runtime_root") or "")
    codelation_root = source / str(adapter.get("codelation_root") or "")
    if not runtime_root.is_dir() or not codelation_root.is_dir():
        raise GermError("platform source is missing its runtime or Codelation genetics")
    shutil.copytree(
        runtime_root,
        runtime,
        ignore=shutil.ignore_patterns(".build", "__pycache__", "*.pyc"),
    )
    target_codelation = runtime / "codelation"
    if target_codelation.exists():
        shutil.rmtree(target_codelation)
    shutil.copytree(
        codelation_root,
        target_codelation,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    germ_console = Path(__file__).resolve().with_name("germ_console.py")
    shutil.copy2(germ_console, runtime / "aurum_germ.py")
    os.chmod(runtime / "aurum_germ.py", 0o755)
    console = runtime / "aurum_console.py"
    if not console.is_file():
        raise GermError("x86 candidate runtime has no bounded Aurum console")
    try:
        bridge.patch_console_file(console)
    except bridge.BridgeError as exc:
        raise GermError(str(exc)) from exc


def _preboot_health(runtime: Path) -> dict[str, Any]:
    py_files = [str(path) for path in runtime.glob("*.py") if path.is_file()]
    if not py_files:
        raise GermError("candidate contains no Python runtime")
    _run([sys.executable, "-m", "py_compile", *py_files], timeout=120)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(runtime)
    env["AURUM_ROOT"] = str(runtime)
    code = (
        "import aurum_console; ok,detail=aurum_console.selftest(); "
        "print(('OK:' if ok else 'FAIL:')+str(detail)); raise SystemExit(0 if ok else 3)"
    )
    detail = _run([sys.executable, "-c", code], env=env, timeout=120)
    return {"compile": "passed", "selftest": detail[-1000:]}


def _arm_trial(slot: str, commit: str) -> dict[str, Any]:
    guardian = Path(__file__).resolve().with_name("guardian.py")
    text = _run(
        [sys.executable, str(guardian), "arm-trial", "--slot", slot, "--commit", commit],
        timeout=30,
    )
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise GermError("guardian did not return valid trial state") from exc


def regrow(*, ref: str, state_root: Path, authorize_network: bool) -> dict[str, Any]:
    if os.geteuid() != 0:
        raise GermError("regrowth requires the root-owned protected germ")
    control = stage(ref=ref, state_root=state_root, authorize_network=authorize_network)
    genetics_path = Path(control["candidate"])
    verified = verify_candidate(genetics_path)
    manifest = verified["manifest"]
    architecture = _architecture()
    adapter = (manifest.get("platforms") or {}).get(architecture)
    if not isinstance(adapter, dict):
        raise GermError(f"current genetics do not declare a platform adapter for {architecture}")

    source_ref = str(adapter.get("source_ref") or "")
    if not source_ref:
        raise GermError("platform genetics do not declare a source_ref")
    sources = state_root / "platform-sources"
    sources.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aurum-platform-", dir=str(state_root)) as temporary:
        work = Path(temporary) / "source"
        source_commit = _fetch_ref(source_ref, work)
        source_destination = sources / source_commit
        if source_destination.exists():
            shutil.rmtree(source_destination)
        os.replace(work, source_destination)

    if adapter.get("local_ab_slots") is not True or adapter.get("growth_adapter") != "python-runtime-slot-v1":
        receipt = {
            "schema": "aurum-regrow-receipt-v1",
            "status": "platform-source-staged",
            "architecture": architecture,
            "genetics_commit": verified["commit"],
            "platform_source_ref": source_ref,
            "platform_source_commit": source_commit,
            "platform_source": str(source_destination),
            "active_overwritten": False,
            "promotion_performed": False,
            "next": "use the Tiny Seed platform adapter; local A/B growth is not yet declared safe for this platform",
        }
        _atomic_json(state_root / "latest-regrow.json", receipt)
        return receipt

    slot_state = _load_slot_state(state_root)
    inactive = "B" if slot_state["active"] == "A" else "A"
    slot_root = SLOTS_ROOT / inactive
    if inactive == slot_state.get("lkg"):
        raise GermError("refusing to replace the Last Known Good slot")

    build_root = state_root / "build"
    build_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"slot-{inactive}-", dir=str(build_root)) as temporary:
        candidate_slot = Path(temporary) / inactive
        runtime = candidate_slot / "opt/aurum"
        runtime.parent.mkdir(parents=True, exist_ok=True)
        _copy_runtime(source_destination, adapter, runtime)
        health = _preboot_health(runtime)
        if slot_root.exists():
            shutil.rmtree(slot_root)
        os.replace(candidate_slot, slot_root)

    guardian = _arm_trial(inactive, source_commit)
    receipt = {
        "schema": "aurum-regrow-receipt-v1",
        "status": "trial-armed",
        "architecture": architecture,
        "genetics_ref": ref,
        "genetics_commit": verified["commit"],
        "platform_source_ref": source_ref,
        "platform_source_commit": source_commit,
        "candidate_slot": inactive,
        "preboot_health": health,
        "guardian": guardian,
        "previous_lkg_preserved": True,
        "active_process_overwritten": False,
        "next": "reboot; germ health service will promote the trial only if the new runtime selftest passes, otherwise it rolls back to LKG",
        "created_at_unix": int(time.time()),
    }
    _atomic_json(state_root / "receipts" / f"regrow-{source_commit}.json", receipt)
    _atomic_json(state_root / "latest-regrow.json", receipt)
    return receipt


def status(state_root: Path) -> dict[str, Any]:
    latest = state_root / "latest-stage.json"
    latest_regrow = state_root / "latest-regrow.json"
    slots = state_root / "slots.json"
    payload: dict[str, Any] = {
        "schema": "aurum-reseed-germ-status-v1",
        "germ_protocol": GERM_PROTOCOL,
        "repository": REPOSITORY,
        "default_ref": DEFAULT_REF,
        "architecture": _architecture(),
        "candidate_only": True,
        "live_overwrite_allowed": False,
        "state_root": str(state_root),
        "latest_stage": None,
        "latest_regrow": None,
        "slots": None,
    }
    for key, path in (("latest_stage", latest), ("latest_regrow", latest_regrow), ("slots", slots)):
        if path.is_file():
            try:
                payload[key] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload[key] = {"status": "unreadable"}
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
            "stage-immutable-genetics",
            "select-hardware-family-adapter",
            "resolve-platform-source",
            "grow-inactive-slot",
            "preboot-health-gate",
            "arm-trial",
            "reboot",
            "postboot-health-gate",
            "promote-or-rollback",
        ],
        "live_overwrite": False,
        "lkg_preserved_until_postboot_health": True,
    }


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Aurum protected reseed germ")
    p.add_argument("command", choices=("status", "plan", "stage", "regrow"))
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
        elif args.command == "stage":
            result = stage(ref=args.ref, state_root=args.state_root, authorize_network=args.authorize_network)
        else:
            result = regrow(ref=args.ref, state_root=args.state_root, authorize_network=args.authorize_network)
    except (GermError, bridge.BridgeError) as exc:
        print(json.dumps({"status": "refused", "detail": str(exc)}, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
