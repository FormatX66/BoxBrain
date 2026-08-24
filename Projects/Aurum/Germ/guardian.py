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
PHYSICAL_HEALTH_TIMEOUT = 150


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
    trial = state.get("trial")
    if trial is not None and trial not in {"A", "B"}:
        raise GuardianError("slot state has invalid trial slot")
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
    if state.get("trial"):
        raise GuardianError("another trial is already pending")
    if slot == state["active"]:
        raise GuardianError("candidate slot is already active")
    if slot == state["lkg"]:
        raise GuardianError("candidate slot may not replace the Last Known Good")
    if not _slot_runtime(slot).is_dir():
        raise GuardianError("candidate runtime is missing")
    if len(commit) != 40 or any(ch not in "0123456789abcdef" for ch in commit.lower()):
        raise GuardianError("candidate commit must be a full immutable SHA")
    # Do not switch /opt/aurum here. The current phenotype remains untouched
    # until the next boot preflight activates the trial.
    state["trial"] = slot
    state["trial_commit"] = commit.lower()
    state["trial_boots"] = 0
    state["trial_armed_at_unix"] = int(time.time())
    state["previous_active"] = state["active"]
    state["last_result"] = "trial-armed-for-next-boot"
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
    state["active"] = trial
    state["trial_boot_started_at_unix"] = int(time.time())
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


def _unit_state(unit: str, *, mode: str) -> str | None:
    systemctl = Path("/bin/systemctl")
    if not systemctl.exists():
        return None
    loaded = subprocess.run(
        [str(systemctl), "show", unit, "--property=LoadState", "--value"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=10,
    ).stdout.strip()
    if loaded in {"", "not-found"}:
        return None
    result = subprocess.run(
        [str(systemctl), mode, unit],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=10,
    )
    return result.stdout.strip() or "unknown"


def _service_health() -> tuple[bool, list[str]]:
    evidence: list[str] = []
    healthy = True

    # One of these launchers should exist on an x86 phenotype. If it exists it
    # must actually be active, not merely "not failed".
    launcher_seen = False
    for unit in ("aurum-pc-console.service", "aurum-tinyseed.service"):
        state = _unit_state(unit, mode="is-active")
        if state is None:
            continue
        launcher_seen = True
        evidence.append(f"{unit}:{state}")
        if state != "active":
            healthy = False

    # Input bootstrap may be absent on older LKGs, but if present it may not be
    # in a hard failed state.
    input_failed = _unit_state("aurum-input-bootstrap.service", mode="is-failed")
    if input_failed is not None:
        evidence.append(f"aurum-input-bootstrap.service:{input_failed}")
        if input_failed == "failed":
            healthy = False

    if not launcher_seen:
        evidence.append("launcher-unit:unavailable")
    return healthy, evidence


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _x86_physical_health(slot: str, state: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """Require fresh first-boot evidence for rich x86 candidates.

    The recent Hopper regression proved that a unit test alone is insufficient:
    the console can be alive while the physical desktop/input path is broken.
    A rich candidate containing aurum_bootstrap.py must therefore produce a
    fresh first-boot assessment and ready input receipt before promotion.
    """
    runtime = _slot_runtime(slot)
    if not (runtime / "aurum_bootstrap.py").is_file():
        return True, {"required": False, "reason": "minimal-bootstrap-or-non-x86-runtime"}

    assessment = Path("/var/lib/aurum/state/first-boot-assessment.json")
    input_receipt = Path("/run/aurum-input-status.json")
    not_before = int(state.get("trial_boot_started_at_unix") or state.get("trial_armed_at_unix") or 0)
    deadline = time.monotonic() + PHYSICAL_HEALTH_TIMEOUT
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            fresh = int(assessment.stat().st_mtime) >= not_before
        except OSError:
            fresh = False
        latest = _read_json(assessment) if fresh else {}
        gui = latest.get("gui") if isinstance(latest.get("gui"), dict) else {}
        desktop = gui.get("desktop") if isinstance(gui.get("desktop"), dict) else {}
        selftest = latest.get("selftest") if isinstance(latest.get("selftest"), dict) else {}
        inp = _read_json(input_receipt)
        physical = bool(gui.get("physical_desktop") or desktop.get("status") == "running")
        input_ready = inp.get("status") == "ready"
        if latest and selftest.get("ok") is True and physical and input_ready:
            return True, {
                "required": True,
                "assessment": str(assessment),
                "selftest": True,
                "physical_desktop": True,
                "input": "ready",
                "gui_status": gui.get("status"),
            }
        # A fresh completed assessment with explicit failed GUI/selftest does
        # not need to consume the rest of the timeout.
        if latest.get("finished_at") and (selftest.get("ok") is False or gui.get("status") == "failed"):
            break
        time.sleep(2)

    return False, {
        "required": True,
        "assessment": str(assessment),
        "latest": latest,
        "input": _read_json(input_receipt),
        "reason": "fresh-physical-health-evidence-not-proven",
    }


def health_check() -> dict[str, Any]:
    state = load_state()
    trial = state.get("trial")
    if not trial:
        return {"status": "steady", **state}
    if state.get("active") != trial:
        return {"status": "waiting", "detail": "trial-not-yet-activated-at-boot", **state}

    ok, detail = _candidate_selftest(trial)
    services_ok, service_evidence = _service_health()
    physical_ok, physical_evidence = _x86_physical_health(trial, state)
    if not ok or not services_ok or not physical_ok:
        if not ok:
            reason = "candidate-selftest-failed"
        elif not services_ok:
            reason = "candidate-critical-service-failed"
        else:
            reason = "candidate-physical-health-unproven"
        rolled = rollback(reason)
        return {
            "status": "rollback",
            "health_detail": detail,
            "service_evidence": service_evidence,
            "physical_evidence": physical_evidence,
            **rolled,
        }
    state["lkg"] = trial
    state["active"] = trial
    state["trial"] = None
    state["trial_commit"] = None
    state["trial_boots"] = 0
    state["last_result"] = "candidate-promoted-healthy"
    state["last_health_detail"] = detail
    state["last_service_evidence"] = service_evidence
    state["last_physical_evidence"] = physical_evidence
    save_state(state)
    return {"status": "promoted", **state}


def _request_reboot() -> None:
    try:
        subprocess.run(["/bin/systemctl", "reboot"], check=False, timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Aurum germ slot guardian")
    p.add_argument("command", choices=("status", "initialize", "arm-trial", "preflight", "health-check", "rollback"))
    p.add_argument("--slot", choices=("A", "B"))
    p.add_argument("--commit")
    p.add_argument("--reason", default="operator-request")
    p.add_argument("--reboot-on-rollback", action="store_true")
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
            result = {"status": "rollback", **rollback(args.reason)}
    except GuardianError as exc:
        print(json.dumps({"status": "refused", "detail": str(exc)}, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    if args.reboot_on_rollback and result.get("status") == "rollback":
        _request_reboot()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
