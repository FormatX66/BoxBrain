#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path

VERSION = "0.01"
TARGET = "raspberry-pi-3"
ROOT = Path("/opt/aurum")
CODELATION = ROOT / "codelation"
STATE = CODELATION / "autobuild" / "native_chain_state.json"


def _read_text(path: Path, default: str = "unknown") -> str:
    try:
        value = path.read_text(encoding="utf-8", errors="replace").replace("\x00", "").strip()
        return value or default
    except OSError:
        return default


def _chain_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def hardware() -> dict:
    memory_kib = "unknown"
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                memory_kib = line.split()[1]
                break
    except OSError:
        pass

    block = []
    try:
        block = sorted(p.name for p in Path("/sys/class/block").iterdir())
    except OSError:
        pass

    net = []
    try:
        net = sorted(p.name for p in Path("/sys/class/net").iterdir())
    except OSError:
        pass

    serial = "unknown"
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith("serial"):
                serial = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass

    return {
        "architecture": platform.machine(),
        "kernel": platform.release(),
        "model": _read_text(Path("/proc/device-tree/model")),
        "serial": serial,
        "memory_kib": memory_kib,
        "block_devices": block,
        "network_interfaces": net,
    }


def selftest() -> tuple[bool, str]:
    field_dir = CODELATION / "field"
    if not field_dir.is_dir():
        return False, "codelation-field-missing"
    sys.path.insert(0, str(field_dir))
    try:
        from local_capability_verification import verify_local_capability_for_gap
        from native_gap_catalog import get_native_semantic_gap

        gap = get_native_semantic_gap("io_safe_port_choice")
        if gap is None:
            return False, "io-safe-port-gap-missing"
        verification = verify_local_capability_for_gap(gap, "io-plan")
        if not verification.verified:
            return False, "io-plan-verification-failed"
        return True, f"io-plan={verification.invocation_output}"
    except Exception as exc:
        return False, f"{type(exc).__name__}:{exc}"


def show_status() -> None:
    state = _chain_state()
    payload = {
        "aurum_pi3_version": VERSION,
        "target": TARGET,
        "substrate": "raspberry-pi-os-hardware-compatibility-layer",
        "hardware": hardware(),
        "aurum": {
            "completed_generations": state.get("completed_generations"),
            "latest_completed_gap": state.get("latest_completed_gap"),
            "next_gap": state.get("next_gap"),
            "blocked_reason": state.get("blocked_reason"),
            "blocked_output": state.get("blocked_output"),
            "trusted_for_continuation": (state.get("workflow_verification") or {}).get("trusted_for_continuation"),
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True), flush=True)


def show_field() -> None:
    state = _chain_state()
    print("AURUM_FIELD", flush=True)
    print("native=" + ",".join(state.get("reusable_native_capabilities") or []), flush=True)
    print("local=" + ",".join(state.get("reusable_local_capabilities") or []), flush=True)


def explicit_power(action: str) -> None:
    print(f"AURUM_PI3_{action.upper()} requested=true", flush=True)
    subprocess.run([f"/sbin/{action}"], check=False)


def main() -> int:
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    ok, detail = selftest()
    hw = hardware()
    print(
        "AURUM_PI3_READY "
        f"version={VERSION} target={TARGET} arch={hw['architecture']} kernel={hw['kernel']} "
        f"selftest={'ok' if ok else 'failed'} detail={detail}",
        flush=True,
    )
    print("Commands: status hardware field selftest reboot poweroff help", flush=True)

    while True:
        try:
            command = input("aurum-pi3> ").strip().lower()
        except EOFError:
            return 0
        except KeyboardInterrupt:
            print("", flush=True)
            continue

        if command in {"", "help", "?"}:
            print("status | hardware | field | selftest | reboot | poweroff | help", flush=True)
        elif command == "status":
            show_status()
        elif command == "hardware":
            print(json.dumps(hardware(), indent=2, sort_keys=True), flush=True)
        elif command == "field":
            show_field()
        elif command == "selftest":
            test_ok, test_detail = selftest()
            print(f"AURUM_SELFTEST status={'ok' if test_ok else 'failed'} detail={test_detail}", flush=True)
        elif command == "reboot":
            explicit_power("reboot")
        elif command == "poweroff":
            explicit_power("poweroff")
        else:
            print("AURUM_UNKNOWN_COMMAND", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
