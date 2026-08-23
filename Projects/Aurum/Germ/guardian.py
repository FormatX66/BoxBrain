#!/usr/bin/env python3
"""Protected A/B runtime-slot guardian for Aurum germ protocol v1.

The guardian owns only the small local continuity mechanism: active slot, LKG,
trial boot accounting, health promotion, and deterministic rollback. It does
not fetch genetics or invent a candidate.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Sequence

STATE_ROOT = Path("/var/lib/aurum/germ")
SLOTS_ROOT = Path("/var/lib/aurum/slots")
ACTIVE_LINK = Path("/opt/aurum")
STATE_FILE = STATE_ROOT / "slots.json"
MAX_TRIAL_BOOTS = 2


class GuardianError(RuntimeError):
    pass


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _slot_runtime(slot: str) -> Path:
    if slot not in {"A", "B"}:
        raise GuardianError("slot must be A or B")
    return SLOTS_ROOT / slot / "opt" / "aurum"


def load_state() -> dict[str, Any]:
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GuardianError(f"slot state unreadable: {exc}") from exc
    if state.get("schema") != "aurum-germ-slots-v1":
        raise GuardianError("unsupported slot-state schema")
    if state.get("active") not in {"A", "B"} or state.get("lkg") not in {"A", "B"}:
        raise GuardianError("slot state has invalid active/LKG")
    return state


def save_state(state: dict[str, Any]) -> None:
    state["updated_at_unix"] = int(time.time())
    _atomic_json(STATE_FILE, state)


def switch_active(slot: str) -> None:
    runtime = _slot_runtime(slot)
    if not runtime.is_dir():
        raise GuardianError(f"slot {slot} runtime is missing")
    ACTIVE_LINK.parent.mkdir(parents=True, exist_ok=True)
    temporary = ACTIVE_LINK.with_name(".aurum.germ-next")
    try:
        temporary.unlink()
    except FileNotFoundError:
        pass
    temporary.symlink_to(runtime)
    os.replace(temporary, ACTIVE_LINK)


def initialize(active: str = "A") -> dict[str, Any]:
    runtime = _slot_runtime(active)
    if not runtime.is_dir():
        raise GuardianError(f"cannot initialize missing slot {active}")
    state = {
        "schema": "aurum-germ-slots-v1",
        "active": active,
        "lkg": active,
        "trial": None,
        "trial_boots": 0,
        "quarantined": [],
        "last_result": "initialized",
    }
    switch_active(active)
    save_state(state)
    return state


def arm_trial(slot: str, *, commit: str) -> dict[str, Any]:
    state = load_state()
    if slot == state["active"]:
        raise GuardianError("candidate slot is already active")
    if not _slot_runtime(slot).is_dir():
        raise GuardianError("candidate runtime is missing")
    if len(commit) != 40 or any(ch not in "0123456789abcdef" for ch in commit.lower()):
        raise GuardianError("candidate commit must be a full immutable SHA")
    state["trial"] = slot
    state["trial_commit"] = commit.lower()
    state["trial_boots"] = 0
    state["previous_active"] = state["active"]
    state["active"] = slot
    state["last_result"] = "trial-armed"
    switch_active(slot)
    save_state(state)
    return state


def rollback(reason: str) -> dict[str, Any]:
    state = load_state()
    failed = state.get("trial") or state.get("active")
    lkg = state["lkg"]
    if failed != lkg:
        quarantined = list(state.get("quarantined") or [])
        record = {"slot": failed, "commit": state.get("trial_commit"), "reason": reason, "at_unix": int(time.time())}
        quarantined.append(record)
        state["quarantined"] = quarantined[-16:]
    state["active"] = lkg
    state["trial"] = None
    state["trial_commit"] = None
    state["trial_boots"] = 0
    state["last_result"] = f"rolled-back:{reason}"
    switch_active(lkg)
    save_state(state)
    return state


def preflight() -> dict[str, Any]:
    state = load_state()
    trial = state.get("trial")
    if not trial:
        try:
            current = ACTIVE_LINK.resolve(strict=True)
        except OSError:
            current = None
        if current != _slot_runtime(state["active"]).resolve():
            switch_active(state["active"])
        return {"status": "steady", **state}
    state["trial_boots"] = int(state.get("trial_boots") or 0) + 1
    if state["trial_boots"] > MAX_TRIAL_BOOTS:
        return {"status": "rollback", **rollback("trial-boot-limit")}
    switch_active(trial)
    state["last_result"] = "trial-booting"
    save_state(state)
    return {"status": "trial", **state}


def _candidate_selftest(slot: str) -> tuple[bool, str]:
    runtime = _slot_runtime(slot)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(runtime)
    env["AURUM_ROOT"] = str(runtime)
    code = (
        "import aurum_console; ok,detail=aurum_console.selftest(); "
        "print(('OK:' if ok else 'FAIL:')+str(detail)); raise SystemExit(0 if ok else 3)"
    )
    try:
        result = subprocess.run(
            ["/usr/bin/python3", "-c", code],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=90,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"selftest-start-failed:{exc}"
    return result.returncode == 0, result.stdout.strip()[-1000:]


def health_check() -> dict[str, Any]:
    state = load_state()
    trial = state.get("trial")
    if not trial:
        return {"status": "steady", **state}
    ok, detail = _candidate_selftest(trial)
    if not ok:
        rolled = rollback("candidate-selftest-failed")
        return {"status": "rollback", "health_detail": detail, **rolled}
    state["lkg"] = trial
    state["active"] = trial
    state["trial"] = None
    state["trial_boots"] = 0
    state["last_result"] = "candidate-promoted-healthy"
    state["last_health_detail"] = detail
    save_state(state)
    return {"status": "promoted", **state}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Aurum germ slot guardian")
    p.add_argument("command", choices=("status", "initialize", "arm-trial", "preflight", "health-check", "rollback"))
    p.add_argument("--slot", choices=("A", "B"))
    p.add_argument("--commit")
    p.add_argument("--reason", default="operator-request")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "status":
            result = load_state()
        elif args.command == "initialize":
            result = initialize()
        elif args.command == "arm-trial":
            if not args.slot or not args.commit:
                raise GuardianError("arm-trial requires --slot and --commit")
            result = arm_trial(args.slot, commit=args.commit)
        elif args.command == "preflight":
            result = preflight()
        elif args.command == "health-check":
            result = health_check()
        else:
            result = rollback(args.reason)
    except GuardianError as exc:
        print(json.dumps({"status": "refused", "detail": str(exc)}, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
