#!/usr/bin/env python3
"""Prepare and verify a controlled physical Guardian rollback drill.

This tool never touches the active/LKG runtime. `arm` replaces only the inactive
slot with a deliberately failing disposable candidate, then arms that candidate
for the next boot. Guardian must quarantine it and restore LKG automatically.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from typing import Any, Sequence


STATE_ROOT = Path(os.environ.get("AURUM_GERM_STATE_ROOT", "/var/lib/aurum/germ"))
SLOTS_ROOT = Path(os.environ.get("AURUM_SLOTS_ROOT", "/var/lib/aurum/slots"))
STATE_FILE = STATE_ROOT / "slots.json"
BACKUP_ROOT = STATE_ROOT / "drill-backups"
RECEIPT = STATE_ROOT / "rollback-drill.json"
DRILL_COMMIT = "d" * 40
CONFIRMATION = "PROVE-LKG-ROLLBACK"


class DrillError(RuntimeError):
    pass


def _read_state() -> dict[str, Any]:
    try:
        value = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DrillError(f"Guardian state unreadable: {exc}") from exc
    if value.get("schema") != "aurum-germ-slots-v1":
        raise DrillError("unsupported Guardian slot schema")
    if value.get("active") not in {"A", "B"} or value.get("lkg") not in {"A", "B"}:
        raise DrillError("invalid active/LKG state")
    return value


def plan() -> dict[str, Any]:
    state = _read_state()
    if state.get("trial"):
        raise DrillError("cannot drill while another trial is pending")
    if state["active"] != state["lkg"]:
        raise DrillError("drill requires steady state with active == LKG")
    inactive = "B" if state["active"] == "A" else "A"
    return {
        "schema": "aurum-rollback-drill-plan-v1",
        "status": "ready-to-arm",
        "active": state["active"],
        "lkg": state["lkg"],
        "disposable_slot": inactive,
        "lkg_will_be_modified": False,
        "active_will_be_modified": False,
        "next": "arm disposable failing candidate, reboot, verify automatic rollback and quarantine",
    }


def _backup(slot: str) -> str | None:
    source = SLOTS_ROOT / slot
    if not source.exists():
        return None
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    path = BACKUP_ROOT / f"{int(time.time())}-{slot}.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        archive.add(source, arcname=slot)
    return str(path)


def arm(confirmation: str) -> dict[str, Any]:
    if os.geteuid() != 0:
        raise DrillError("rollback drill arming requires root")
    if confirmation != CONFIRMATION:
        raise DrillError(f"arm requires --confirm {CONFIRMATION}")
    details = plan()
    slot = str(details["disposable_slot"])
    slot_root = SLOTS_ROOT / slot
    backup = _backup(slot)
    if slot_root.exists():
        shutil.rmtree(slot_root)
    runtime = slot_root / "opt" / "aurum"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "aurum_console.py").write_text(
        "def selftest():\n    return False, 'intentional-guardian-rollback-drill'\n",
        encoding="utf-8",
    )

    guardian = Path(__file__).resolve().with_name("guardian.py")
    result = subprocess.run(
        [sys.executable, str(guardian), "arm-trial", "--slot", slot, "--commit", DRILL_COMMIT],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        raise DrillError(result.stdout.strip()[-1200:] or "Guardian refused drill candidate")
    receipt = {
        "schema": "aurum-rollback-drill-receipt-v1",
        "status": "armed",
        "drill_commit": DRILL_COMMIT,
        "disposable_slot": slot,
        "backup": backup,
        "armed_at_unix": int(time.time()),
        "next": "reboot and then run rollback_drill.py verify",
    }
    RECEIPT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def verify() -> dict[str, Any]:
    state = _read_state()
    try:
        receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DrillError(f"drill receipt unavailable: {exc}") from exc
    slot = receipt.get("disposable_slot")
    quarantined = state.get("quarantined") or []
    match = next(
        (
            item for item in reversed(quarantined)
            if isinstance(item, dict)
            and item.get("slot") == slot
            and item.get("commit") == DRILL_COMMIT
        ),
        None,
    )
    ok = (
        state.get("active") == state.get("lkg")
        and state.get("trial") is None
        and isinstance(match, dict)
    )
    if not ok:
        raise DrillError("automatic rollback/quarantine has not been proven yet")
    result = {
        "schema": "aurum-rollback-drill-proof-v1",
        "status": "RECOVERY_PROVEN",
        "active": state.get("active"),
        "lkg": state.get("lkg"),
        "quarantine": match,
        "lkg_preserved": True,
        "verified_at_unix": int(time.time()),
    }
    RECEIPT.write_text(json.dumps({**receipt, "proof": result}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Aurum controlled Guardian rollback drill")
    p.add_argument("command", choices=("plan", "arm", "verify"))
    p.add_argument("--confirm", default="")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = plan() if args.command == "plan" else arm(args.confirm) if args.command == "arm" else verify()
    except DrillError as exc:
        print(json.dumps({"status": "refused", "detail": str(exc)}, indent=2, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
