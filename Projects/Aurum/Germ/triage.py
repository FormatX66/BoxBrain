#!/usr/bin/env python3
"""Read-only Tiny Seed failure triage.

This tool gathers a small non-secret machine snapshot and ranks the most likely
critical-path failure family. It never changes slots, disks, networking, or
recovery state. The receipt is intended to make a terse physical report such as
"it didn't work" actionable without starting diagnosis from scratch.
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Any

EVIDENCE_ROOT = Path("/var/lib/aurum/evidence")
SLOTS = Path("/var/lib/aurum/germ/slots.json")
BOOT_PROOF = EVIDENCE_ROOT / "boot-proof.json"
LATEST_REGROW = Path("/var/lib/aurum/germ/latest-regrow.json")


def _run(args: list[str], timeout: int = 8) -> dict[str, Any]:
    try:
        result = subprocess.run(
            args,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
        )
        return {
            "returncode": result.returncode,
            "output": result.stdout.strip()[-4000:],
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {"returncode": None, "output": f"unavailable:{type(exc).__name__}"}


def _json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _unit(name: str) -> str:
    result = _run(["systemctl", "is-active", name])
    output = str(result.get("output") or "").splitlines()
    return output[-1] if output else "unavailable"


def collect() -> dict[str, Any]:
    route = _run(["ip", "route", "show", "default"])
    nm = _run(["nmcli", "-t", "-f", "STATE", "general"])
    disks = _run(["lsblk", "--json", "--paths", "--output", "PATH,TYPE,SIZE,MODEL,TRAN,MOUNTPOINTS"])
    cmdline = ""
    try:
        cmdline = Path("/proc/cmdline").read_text(encoding="utf-8").strip()
    except OSError:
        pass
    return {
        "schema": "aurum-tinyseed-triage-v1",
        "observed_at_unix": int(time.time()),
        "machine": {
            "architecture": platform.machine(),
            "hostname": platform.node(),
            "kernel": platform.release(),
            "cmdline": cmdline,
        },
        "boot_proof": _json(BOOT_PROOF),
        "guardian": _json(SLOTS),
        "latest_regrow": _json(LATEST_REGROW),
        "network": {
            "network_manager": nm,
            "default_route": route,
        },
        "services": {
            "aurum-germ-preflight.service": _unit("aurum-germ-preflight.service"),
            "aurum-germ-health.service": _unit("aurum-germ-health.service"),
            "aurum-tinyseed.service": _unit("aurum-tinyseed.service"),
            "aurum-boot-proof.service": _unit("aurum-boot-proof.service"),
            "NetworkManager.service": _unit("NetworkManager.service"),
        },
        "disks": disks,
    }


def classify(snapshot: dict[str, Any]) -> dict[str, str]:
    guardian = snapshot.get("guardian")
    services = snapshot.get("services") if isinstance(snapshot.get("services"), dict) else {}
    network = snapshot.get("network") if isinstance(snapshot.get("network"), dict) else {}
    latest_regrow = snapshot.get("latest_regrow")

    if snapshot.get("boot_proof") is None:
        return {
            "code": "BOOT_PROOF_MISSING",
            "next": "Use the safe/verbose boot path or capture the first visible boot error; do not modify LKG.",
        }

    if not isinstance(guardian, dict) or guardian.get("active") not in {"A", "B"} or guardian.get("lkg") not in {"A", "B"}:
        return {
            "code": "GUARDIAN_STATE_INVALID",
            "next": "Stop mutation and repair the protected germ/LKG metadata from Tiny Seed.",
        }

    route = network.get("default_route") if isinstance(network.get("default_route"), dict) else {}
    nm = network.get("network_manager") if isinstance(network.get("network_manager"), dict) else {}
    if route.get("returncode") != 0 or not str(route.get("output") or "").strip() or "connected" not in str(nm.get("output") or "").lower():
        return {
            "code": "NETWORK_NOT_READY",
            "next": "Keep the protected germ/LKG unchanged and repair Ethernet/Wi-Fi before regrow.",
        }

    if services.get("aurum-tinyseed.service") not in {"active", "activating"}:
        return {
            "code": "TINYSEED_SERVICE_NOT_ACTIVE",
            "next": "Inspect the Tiny Seed service journal; do not proceed to install/regrow until the setup surface is healthy.",
        }

    if isinstance(latest_regrow, dict):
        status = str(latest_regrow.get("status") or "")
        if status and status not in {"trial-armed", "platform-source-staged"}:
            return {
                "code": "REGROW_INCOMPLETE",
                "next": "Use the saved regrow receipt to repair fetch/build/platform staging, then retry only the inactive slot.",
            }

    if str(guardian.get("last_result") or "").startswith("rolled-back:"):
        return {
            "code": "CANDIDATE_ROLLED_BACK",
            "next": "Treat rollback as successful protection; inspect quarantine/health evidence and fix the candidate before another trial.",
        }

    return {
        "code": "BASELINE_HEALTHY",
        "next": "The basic seed, Guardian and network evidence look healthy; continue with the next gated operation.",
    }


def main() -> int:
    snapshot = collect()
    snapshot["classification"] = classify(snapshot)
    try:
        EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
        temporary = EVIDENCE_ROOT / f".triage-{os.getpid()}.tmp"
        temporary.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, EVIDENCE_ROOT / "triage-latest.json")
    except OSError:
        pass
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    print(f"AURUM_TRIAGE code={snapshot['classification']['code']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
