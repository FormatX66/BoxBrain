#!/usr/bin/env python3
"""Aurum PC first-boot entry point with exact-machine evidence and autonomous assessment."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import aurum_console
from aurum_boot_screen import BootScreen
from aurum_gui_runtime import GuiRuntime, GuiRuntimeError
from aurum_hardware import DEFAULT_PLAN, DEFAULT_PROFILE, capture_hardware_evidence, collect_hardware_profile
from aurum_network import ensure_online, wireless_interfaces
from aurum_time import synchronize_clock
from aurum_wifi_diag import diagnose as diagnose_wifi
from aurum_wifi_recovery import recover_existing_wifi_driver
from aurum_workspace import WorkspaceError

STATE_DIR = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
ASSESSMENT = STATE_DIR / "first-boot-assessment.json"
INPUT_STATUS = Path("/run/aurum-input-status.json")
POLICY = Path(__file__).with_name("pc01_autonomy_policy.json")


def _write_assessment(payload: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = ASSESSMENT.with_name(f".{ASSESSMENT.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, ASSESSMENT)


def _primary_console() -> bool:
    return os.environ.get("AURUM_PRIMARY_CONSOLE", "0") == "1"


def _autonomous_first_boot_enabled() -> bool:
    return _primary_console() and os.environ.get("AURUM_DISABLE_AUTONOMOUS_FIRST_BOOT", "0") != "1"


def _json_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _input_summary() -> tuple[str, str]:
    payload = _json_file(INPUT_STATUS)
    pointers = len(payload.get("pointers") or [])
    touchpads = len(payload.get("touchpads") or [])
    wake = payload.get("wake_policy") if isinstance(payload.get("wake_policy"), dict) else {}
    if payload.get("status") == "ready":
        return "ready", f"{pointers} pointer(s), {touchpads} trackpad(s), wake {wake.get('status', 'observed')}"
    if not payload:
        return "degraded", "input bootstrap receipt unavailable"
    return "degraded", f"{payload.get('status', 'unknown')}, {pointers} pointer(s)"


def _start_gui() -> dict[str, Any]:
    policy = _json_file(POLICY)
    if policy.get("auto_gui_start") is not True:
        return {"status": "skipped", "reason": "automatic-gui-disabled"}
    try:
        return GuiRuntime().start()
    except (GuiRuntimeError, OSError) as exc:
        return {"status": "failed", "detail": f"{type(exc).__name__}:{exc}"}


def _first_boot(
    profile: dict[str, Any],
    plan: dict[str, Any],
    screen: BootScreen | None = None,
) -> None:
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

    primary = _primary_console()
    if primary:
        # The installed runtime is bundled locally. Neither Wi-Fi, DNS, Git,
        # nor a text prompt is a prerequisite for the physical GUI. Network
        # reconnect and forward sync have their own supervised services.
        if screen:
            screen.update("desktop", "active")
        assessment["gui"] = _start_gui()
        desktop = assessment["gui"].get("desktop")
        desktop = desktop if isinstance(desktop, dict) else {}
        physical = bool(assessment["gui"].get("physical_desktop") or desktop.get("status") == "running")
        if screen:
            screen.update("desktop", "ready" if physical else "degraded",
                          "physical surface ready" if physical else assessment["gui"].get("status", "unavailable"))
        network = {"status": "background-network-service", "online": None}
    else:
        if screen:
            screen.update("network", "active")
        print("AURUM_FIRST_BOOT stage=network status=starting", flush=True)
        try:
            network = ensure_online(interactive=False)
        except Exception as exc:
            network = {"status": "failed", "online": False, "detail": f"{type(exc).__name__}:{exc}"}
    assessment["network"] = network
    if screen:
        screen.update(
            "network",
            "ready" if network.get("online") else ("active" if network.get("online") is None else "degraded"),
            network.get("status"),
        )
    online_label = str(network["online"]).lower() if isinstance(network.get("online"), bool) else "unknown"
    print(
        "AURUM_FIRST_BOOT "
        f"stage=network status={network.get('status')} online={online_label}",
        flush=True,
    )

    # Basic DNS/TCP probing does not depend on TLS.  Once networking is alive,
    # correct a potentially stale firmware/RTC clock before HTTPS Git traffic.
    if primary:
        assessment["clock"] = {"status": "background-sync-service", "synchronized": None}
        assessment["git_sync"] = {"status": "background-sync-service"}
    elif network.get("online"):
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

    if screen:
        screen.update("workspace", "active")
    try:
        assessment["seed"] = aurum_console.WORKSPACE.seed()
    except WorkspaceError as exc:
        assessment["seed"] = {"status": "failed", "detail": str(exc)}

    if screen:
        screen.update("workspace", "ready" if assessment["seed"].get("status") != "failed" else "degraded")
        screen.update("verification", "active")
    test_ok, test_detail = aurum_console.selftest()
    assessment["selftest"] = {"ok": test_ok, "detail": test_detail}

    # Local-first, resumable build is deliberately independent of Internet.
    # A missing Wi-Fi driver, DHCP, DNS, NTP, or GitHub must not stop it.
    assessment["self_build"] = aurum_console.BUILDS.start()
    if screen:
        screen.update("verification", "ready" if test_ok else "degraded", assessment["self_build"].get("status"))

    assessment["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write_assessment(assessment)
    print(
        "AURUM_FIRST_BOOT "
        f"status=assessment-complete selftest={'ok' if test_ok else 'failed'} "
        f"build={assessment['self_build'].get('status')} evidence={ASSESSMENT}",
        flush=True,
    )


def main() -> int:
    screen = BootScreen(enabled=_primary_console())
    profile: dict[str, Any] = {}
    plan: dict[str, Any] = {}
    screen.update("hardware", "active")
    try:
        profile, plan = capture_hardware_evidence()
        screen.update("hardware", "ready", f"{len(profile['input_devices'])} input device(s)")
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
        screen.update("hardware", "degraded", type(exc).__name__)
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

    input_state, input_detail = _input_summary()
    screen.update("input", input_state, input_detail)

    if profile and plan:
        _first_boot(profile, plan, screen)
    else:
        for stage in ("network", "workspace", "verification", "desktop"):
            screen.update(stage, "skipped", "hardware evidence unavailable")

    screen.finish(
        "ready" if screen.states["desktop"] == "ready" else "degraded",
        "Hopper desktop is ready" if screen.states["desktop"] == "ready" else "Recovery console is available",
    )

    # Force the bounded console hardware command to use the detailed read-only
    # provider.  The boot image is stateless during physical discovery so an
    # older root-overlay cannot replace this provider.
    aurum_console.hardware = collect_hardware_profile
    return aurum_console.main()


if __name__ == "__main__":
    raise SystemExit(main())
