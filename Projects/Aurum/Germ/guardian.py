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

import recovery_ledger

STATE_ROOT = Path(os.environ.get("AURUM_GERM_STATE_ROOT", "/var/lib/aurum/germ"))
SLOTS_ROOT = Path(os.environ.get("AURUM_SLOTS_ROOT", "/var/lib/aurum/slots"))
ACTIVE_LINK = Path(os.environ.get("AURUM_ACTIVE_LINK", "/opt/aurum"))
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


def _prepare_change(
    change: str,
    state: dict[str, Any],
    requested: dict[str, Any] | None = None,
    *,
    recovery_critical: bool = False,
) -> dict[str, Any] | None:
    try:
        return recovery_ledger.prepare_change(
            state_root=STATE_ROOT,
            slots_root=SLOTS_ROOT,
            active_link=ACTIVE_LINK,
            change=change,
            state=state,
            requested=requested,
        )
    except recovery_ledger.LedgerError as exc:
        if recovery_critical:
            return {"warning": str(exc)}
        raise GuardianError(str(exc)) from exc


def _commit_change(
    change: str,
    *,
    before: dict[str, Any] | None,
    after: dict[str, Any],
    prepared: dict[str, Any] | None,
    requested: dict[str, Any] | None,
    validation: dict[str, Any] | None,
    outcome: str,
) -> None:
    try:
        recovery_ledger.commit_change(
            state_root=STATE_ROOT,
            change=change,
            before=before,
            after=after,
            prepared=prepared if prepared and "checkpoint" in prepared else None,
            requested=requested,
            validation=validation,
            outcome=outcome,
        )
    except recovery_ledger.LedgerError:
        # A prepared record already exists before forward mutations. Rollback
        # must never be blocked merely because its final receipt cannot land.
        pass


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
        "previous_lkg": None,
        "trial": None,
        "trial_boots": 0,
        "quarantined": [],
        "last_result": "initialized",
    }
    switch_active(active)
    save_state(state)
    prepared = _prepare_change("initialize-lkg", state, {"active_slot": active}, recovery_critical=True)
    _commit_change(
        "initialize-lkg",
        before=None,
        after=state,
        prepared=prepared,
        requested={"active_slot": active},
        validation={"lkg_runtime_present": runtime.is_dir()},
        outcome="initialized",
    )
    return state


def arm_trial(
    slot: str,
    *,
    commit: str,
    genetics_commit: str | None = None,
    manifest_identity: str | None = None,
) -> dict[str, Any]:
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
    if genetics_commit is not None and (
        len(genetics_commit) != 40
        or any(ch not in "0123456789abcdef" for ch in genetics_commit.lower())
    ):
        raise GuardianError("genetics commit must be a full immutable SHA")
    if manifest_identity is not None and not (1 <= len(manifest_identity) <= 160):
        raise GuardianError("manifest identity is invalid")
    before = dict(state)
    requested = {
        "candidate_slot": slot,
        "platform_commit": commit.lower(),
        "genetics_commit": genetics_commit.lower() if genetics_commit else None,
        "manifest_identity": manifest_identity,
    }
    prepared = _prepare_change("arm-trial", state, requested)
    # Do not switch /opt/aurum here. The current phenotype remains untouched
    # until the next boot preflight activates the trial.
    state["trial"] = slot
    state["trial_commit"] = commit.lower()
    state["trial_genetics_commit"] = genetics_commit.lower() if genetics_commit else None
    state["trial_manifest_identity"] = manifest_identity
    state["trial_boots"] = 0
    state["trial_armed_at_unix"] = int(time.time())
    state["previous_active"] = state["active"]
    state["last_result"] = "trial-armed-for-next-boot"
    save_state(state)
    _commit_change(
        "arm-trial",
        before=before,
        after=state,
        prepared=prepared,
        requested=requested,
        validation={"candidate_runtime_present": _slot_runtime(slot).is_dir()},
        outcome="trial-armed-for-next-boot",
    )
    return state


def rollback(reason: str) -> dict[str, Any]:
    state = load_state()
    before = dict(state)
    failed = state.get("trial") or state.get("active")
    lkg = state["lkg"]
    if failed != lkg:
        quarantined = list(state.get("quarantined") or [])
        record = {
            "slot": failed,
            "commit": state.get("trial_commit"),
            "genetics_commit": state.get("trial_genetics_commit"),
            "manifest_identity": state.get("trial_manifest_identity"),
            "reason": reason,
            "at_unix": int(time.time()),
        }
        quarantined.append(record)
        state["quarantined"] = quarantined[-16:]
    state["active"] = lkg
    requested = {"failed_slot": failed, "restore_lkg": lkg, "reason": reason}
    prepared = _prepare_change("rollback-to-lkg", before, requested, recovery_critical=True)
    state["trial"] = None
    state["trial_commit"] = None
    state["trial_genetics_commit"] = None
    state["trial_manifest_identity"] = None
    state["trial_boots"] = 0
    state["last_result"] = f"rolled-back:{reason}"
    switch_active(lkg)
    save_state(state)
    _commit_change(
        "rollback-to-lkg",
        before=before,
        after=state,
        prepared=prepared,
        requested=requested,
        validation={"lkg_runtime_present": _slot_runtime(lkg).is_dir()},
        outcome=state["last_result"],
    )
    return state


def restore_previous(reason: str) -> dict[str, Any]:
    state = load_state()
    if state.get("trial") is not None or state.get("active") != state.get("lkg"):
        raise GuardianError("previous restore requires steady active/LKG state")
    previous = state.get("previous_lkg")
    if previous not in {"A", "B"} or previous == state.get("lkg"):
        raise GuardianError("previous proven slot is unavailable")
    if not _slot_runtime(previous).is_dir():
        raise GuardianError("previous proven runtime is missing")
    before = dict(state)
    current = str(state["lkg"])
    requested = {"from_lkg": current, "restore_previous": previous, "reason": reason}
    prepared = _prepare_change("restore-previous-lkg", before, requested, recovery_critical=True)
    current_commit = state.get("lkg_commit")
    current_genetics = state.get("lkg_genetics_commit")
    current_manifest = state.get("lkg_manifest_identity")
    state["active"] = previous
    state["lkg"] = previous
    state["lkg_commit"] = state.get("previous_lkg_commit")
    state["lkg_genetics_commit"] = state.get("previous_lkg_genetics_commit")
    state["lkg_manifest_identity"] = state.get("previous_lkg_manifest_identity")
    state["previous_lkg"] = current
    state["previous_lkg_commit"] = current_commit
    state["previous_lkg_genetics_commit"] = current_genetics
    state["previous_lkg_manifest_identity"] = current_manifest
    state["last_result"] = f"restored-previous:{reason}"
    switch_active(previous)
    save_state(state)
    _commit_change(
        "restore-previous-lkg",
        before=before,
        after=state,
        prepared=prepared,
        requested=requested,
        validation={"previous_runtime_present": True},
        outcome=state["last_result"],
    )
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
            before = dict(state)
            requested = {"active_slot": state["active"], "observed_link": str(current) if current else None}
            prepared = _prepare_change("repair-active-link", before, requested, recovery_critical=True)
            switch_active(state["active"])
            _commit_change(
                "repair-active-link",
                before=before,
                after=state,
                prepared=prepared,
                requested=requested,
                validation={"active_runtime_present": _slot_runtime(state["active"]).is_dir()},
                outcome="active-link-repaired",
            )
        return {"status": "steady", **state}

    before = dict(state)
    next_trial_boot = int(state.get("trial_boots") or 0) + 1
    if next_trial_boot > MAX_TRIAL_BOOTS:
        return {"status": "rollback", **rollback("trial-boot-limit")}

    requested = {"trial_slot": trial, "trial_boot": next_trial_boot}
    prepared = _prepare_change("activate-trial", before, requested)
    state["trial_boots"] = next_trial_boot
    switch_active(trial)
    state["active"] = trial
    state["trial_boot_started_at_unix"] = int(time.time())
    state["last_result"] = "trial-booting"
    save_state(state)
    _commit_change(
        "activate-trial",
        before=before,
        after=state,
        prepared=prepared,
        requested=requested,
        validation={"trial_boot_within_limit": True},
        outcome="trial-booting",
    )
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
    before = dict(state)
    requested = {
        "candidate_slot": trial,
        "platform_commit": state.get("trial_commit"),
        "genetics_commit": state.get("trial_genetics_commit"),
        "manifest_identity": state.get("trial_manifest_identity"),
    }
    validation = {
        "selftest": ok,
        "services": services_ok,
        "physical": physical_ok,
        "service_evidence": service_evidence,
        "physical_evidence": physical_evidence,
    }
    prepared = _prepare_change("promote-healthy-candidate", before, requested)
    state["previous_lkg"] = state.get("lkg")
    state["previous_lkg_commit"] = state.get("lkg_commit")
    state["previous_lkg_genetics_commit"] = state.get("lkg_genetics_commit")
    state["previous_lkg_manifest_identity"] = state.get("lkg_manifest_identity")
    state["lkg"] = trial
    state["lkg_commit"] = state.get("trial_commit")
    state["lkg_genetics_commit"] = state.get("trial_genetics_commit")
    state["lkg_manifest_identity"] = state.get("trial_manifest_identity")
    state["active"] = trial
    state["trial"] = None
    state["trial_commit"] = None
    state["trial_genetics_commit"] = None
    state["trial_manifest_identity"] = None
    state["trial_boots"] = 0
    state["last_result"] = "candidate-promoted-healthy"
    state["last_health_detail"] = detail
    state["last_service_evidence"] = service_evidence
    state["last_physical_evidence"] = physical_evidence
    save_state(state)
    _commit_change(
        "promote-healthy-candidate",
        before=before,
        after=state,
        prepared=prepared,
        requested=requested,
        validation=validation,
        outcome="candidate-promoted-healthy",
    )
    return {"status": "promoted", **state}


def checkpoint(
    change: str,
    *,
    slot: str | None = None,
    commit: str | None = None,
    genetics_commit: str | None = None,
    manifest_identity: str | None = None,
) -> dict[str, Any]:
    for label, value in (("platform", commit), ("genetics", genetics_commit)):
        if value is not None and (
            len(value) != 40 or any(character not in "0123456789abcdef" for character in value.lower())
        ):
            raise GuardianError(f"{label} commit must be a full immutable SHA")
    if manifest_identity is not None and not (1 <= len(manifest_identity) <= 160):
        raise GuardianError("manifest identity is invalid")
    state = load_state()
    requested = {
        "candidate_slot": slot,
        "platform_commit": commit,
        "genetics_commit": genetics_commit,
        "manifest_identity": manifest_identity,
    }
    prepared = _prepare_change(change, state, requested)
    return {"status": "checkpointed", "change": change, **(prepared or {})}


def _request_reboot() -> None:
    try:
        subprocess.run(["/bin/systemctl", "reboot"], check=False, timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Aurum germ slot guardian")
    p.add_argument(
        "command",
        choices=(
            "status",
            "initialize",
            "checkpoint",
            "arm-trial",
            "preflight",
            "health-check",
            "rollback",
            "restore-previous",
        ),
    )
    p.add_argument("--slot", choices=("A", "B"))
    p.add_argument("--commit")
    p.add_argument("--genetics-commit")
    p.add_argument("--manifest-identity")
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
        elif args.command == "checkpoint":
            result = checkpoint(
                args.reason,
                slot=args.slot,
                commit=args.commit,
                genetics_commit=args.genetics_commit,
                manifest_identity=args.manifest_identity,
            )
        elif args.command == "arm-trial":
            if not args.slot or not args.commit:
                raise GuardianError("arm-trial requires --slot and --commit")
            result = arm_trial(
                args.slot,
                commit=args.commit,
                genetics_commit=args.genetics_commit,
                manifest_identity=args.manifest_identity,
            )
        elif args.command == "preflight":
            result = preflight()
        elif args.command == "health-check":
            result = health_check()
        elif args.command == "rollback":
            result = {"status": "rollback", **rollback(args.reason)}
        else:
            result = {"status": "restored-previous", **restore_previous(args.reason)}
    except GuardianError as exc:
        print(json.dumps({"status": "refused", "detail": str(exc)}, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    if args.reboot_on_rollback and result.get("status") == "rollback":
        _request_reboot()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
