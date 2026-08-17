#!/usr/bin/env python3
"""Aurum PC first-boot entry point with exact-machine evidence and autonomous assessment."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import aurum_console
from aurum_hardware import DEFAULT_PLAN, DEFAULT_PROFILE, capture_hardware_evidence, collect_hardware_profile
from aurum_network import ensure_online, wireless_interfaces
from aurum_time import synchronize_clock
from aurum_wifi_diag import diagnose as diagnose_wifi
from aurum_wifi_recovery import recover_existing_wifi_driver
from aurum_workspace import WorkspaceError

STATE_DIR = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
ASSESSMENT = STATE_DIR / "first-boot-assessment.json"


def _write_assessment(payload: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = ASSESSMENT.with_name(f".{ASSESSMENT.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, ASSESSMENT)


def _primary_console() -> bool:
    return os.environ.get("AURUM_PRIMARY_CONSOLE", "0") == "1"


def _autonomous_first_boot_enabled() -> bool:
    return _primary_console() and os.environ.get("AURUM_DISABLE_AUTONOMOUS_FIRST_BOOT", "0") != "1"


def _first_boot(profile: dict[str, Any], plan: dict[str, Any]) -> None:
    if not _autonomous_first_boot_enabled():
        print("AURUM_FIRST_BOOT status=delegated-or-disabled", flush=True)
        return

    assessment: dict[str, Any] = {
        "schema": "aurum-x86-first-boot-assessment-v2",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hardware_profile": str(DEFAULT_PROFILE),
        "kernel_driver_plan": str(DEFAULT_PLAN),
        "observed": {
            "pci": len(profile.get("pci_devices") or []),
            "usb": len(profile.get("usb_devices") or []),
            "block": len(profile.get("block_devices") or []),
            "input": len(profile.get("input_devices") or []),
            "graphics": len(profile.get("graphics_devices") or []),
            "network": len(profile.get("network_interfaces") or []),
            "existing_drivers": len(plan.get("required_existing_drivers") or []),
            "unresolved_devices": len(plan.get("unresolved_devices") or []),
        },
    }

    print("AURUM_FIRST_BOOT stage=network status=starting", flush=True)
    try:
        network = ensure_online(interactive=True)
    except Exception as exc:
        network = {"status": "failed", "online": False, "detail": f"{type(exc).__name__}:{exc}"}
    assessment["network"] = network
    print(
        "AURUM_FIRST_BOOT "
        f"stage=network status={network.get('status')} online={str(bool(network.get('online'))).lower()}",
        flush=True,
    )

    # Basic DNS/TCP probing does not depend on TLS.  Once networking is alive,
    # correct a potentially stale firmware/RTC clock before HTTPS Git traffic.
    if network.get("online"):
        try:
            clock = synchronize_clock()
        except Exception as exc:
            clock = {"status": "failed", "synchronized": False, "detail": f"{type(exc).__name__}:{exc}"}
        assessment["clock"] = clock
        print(
            "AURUM_FIRST_BOOT "
            f"stage=clock status={clock.get('status')} synchronized={str(bool(clock.get('synchronized'))).lower()}",
            flush=True,
        )
        try:
            assessment["git_sync"] = aurum_console.WORKSPACE.git_sync(authorize_network=True)
        except WorkspaceError as exc:
            assessment["git_sync"] = {"status": "degraded", "detail": str(exc)}
    else:
        assessment["clock"] = {"status": "offline-not-required-for-local-build", "synchronized": False}
        assessment["git_sync"] = {"status": "offline-bundled-source"}

    try:
        assessment["seed"] = aurum_console.WORKSPACE.seed()
    except WorkspaceError as exc:
        assessment["seed"] = {"status": "failed", "detail": str(exc)}

    test_ok, test_detail = aurum_console.selftest()
    assessment["selftest"] = {"ok": test_ok, "detail": test_detail}

    # Local-first, resumable build is deliberately independent of Internet.
    # A missing Wi-Fi driver, DHCP, DNS, NTP, or GitHub must not stop it.
    assessment["self_build"] = aurum_console.BUILDS.start()
    assessment["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write_assessment(assessment)
    print(
        "AURUM_FIRST_BOOT "
        f"status=assessment-complete selftest={'ok' if test_ok else 'failed'} "
        f"build={assessment['self_build'].get('status')} evidence={ASSESSMENT}",
        flush=True,
    )


def main() -> int:
    profile: dict[str, Any] = {}
    plan: dict[str, Any] = {}
    try:
        profile, plan = capture_hardware_evidence()
        print(
            "AURUM_HARDWARE_PROFILE "
            f"status=ready profile={DEFAULT_PROFILE} plan={DEFAULT_PLAN} "
            f"pci={len(profile['pci_devices'])} usb={len(profile['usb_devices'])} "
            f"block={len(profile['block_devices'])} input={len(profile['input_devices'])} "
            f"graphics={len(profile['graphics_devices'])} net={len(profile['network_interfaces'])} "
            f"drivers={len(plan['required_existing_drivers'])} unresolved={len(plan['unresolved_devices'])}",
            flush=True,
        )
    except Exception as exc:
        print(
            "AURUM_HARDWARE_PROFILE "
            f"status=degraded detail={json.dumps(type(exc).__name__ + ':' + str(exc))}",
            flush=True,
        )

    # Diagnose missing Wi-Fi on every console, including the deterministic VM
    # serial console.  On the physical primary console first try only existing
    # kernel modules resolved from an unbound wireless modalias; never unload or
    # replace a bound driver here.
    if profile and not wireless_interfaces():
        recovery: dict[str, Any] = {"status": "diagnostic-only"}
        if _autonomous_first_boot_enabled():
            try:
                recovery = recover_existing_wifi_driver()
            except Exception as exc:
                recovery = {"status": "failed", "detail": f"{type(exc).__name__}:{exc}"}
            print("AURUM_WIFI_RECOVERY " + json.dumps(recovery, sort_keys=True), flush=True)
        if not wireless_interfaces():
            wifi_diag = diagnose_wifi()
            print("AURUM_WIFI_DIAG " + json.dumps(wifi_diag, sort_keys=True), flush=True)

    if profile and plan:
        _first_boot(profile, plan)

    # Force the bounded console hardware command to use the detailed read-only
    # provider.  The boot image is stateless during physical discovery so an
    # older root-overlay cannot replace this provider.
    aurum_console.hardware = collect_hardware_profile
    return aurum_console.main()


if __name__ == "__main__":
    raise SystemExit(main())
