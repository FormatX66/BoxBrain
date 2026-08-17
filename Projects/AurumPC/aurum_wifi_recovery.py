#!/usr/bin/env python3
"""Conservative recovery for a Wi-Fi controller that exists but did not bind.

This lane never invents a driver, replaces a bound driver, unloads a module, or
writes device registers directly.  It resolves an unbound PCI network-controller
modalias against modules already supplied by the seed kernel and asks modprobe
to load those existing modules.  If that does not produce a wireless interface,
it stops and returns evidence for the driver-synthesis lane.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from aurum_hardware import collect_hardware_profile
from aurum_network import wireless_interfaces


def _run(arguments: list[str], timeout: int = 15) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )


def _wifi_candidates(profile: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for device in profile.get("pci_devices", []):
        pci_class = str(device.get("class") or "").lower()
        # PCI base class 02, subclass 80 is the common wireless/other-network
        # controller shape.  Do not touch subclass 00 Ethernet here.
        if pci_class.startswith("0x0280"):
            result.append(device)
    return result


def _kernel_messages() -> list[str]:
    dmesg = shutil.which("dmesg")
    if not dmesg:
        return []
    result = _run([dmesg, "--color=never"], timeout=10)
    if result.returncode != 0:
        return []
    tokens = ("firmware", "wifi", "wlan", "802.11", "iwlwifi", "rtw", "ath", "brcm", "mt76")
    lines = [line for line in result.stdout.splitlines() if any(token in line.lower() for token in tokens)]
    return lines[-40:]


def recover_existing_wifi_driver(*, settle_seconds: int = 8) -> dict[str, Any]:
    before = wireless_interfaces()
    if before:
        return {"status": "already-present", "interfaces": before, "attempts": [], "read_only_evidence": True}

    profile = collect_hardware_profile()
    candidates = _wifi_candidates(profile)
    modprobe = shutil.which("modprobe")
    attempts: list[dict[str, Any]] = []
    if not modprobe:
        return {
            "status": "modprobe-unavailable",
            "interfaces": [],
            "candidates": candidates,
            "attempts": attempts,
            "kernel_messages": _kernel_messages(),
        }

    for candidate in candidates:
        if candidate.get("driver"):
            attempts.append({
                "address": candidate.get("address"),
                "status": "already-bound-no-interface",
                "driver": candidate.get("driver"),
                "modalias": candidate.get("modalias"),
            })
            continue
        modalias = str(candidate.get("modalias") or "").strip()
        if not modalias:
            attempts.append({"address": candidate.get("address"), "status": "no-modalias"})
            continue
        resolved = _run([modprobe, "--resolve-alias", modalias], timeout=10)
        modules = [line.strip() for line in resolved.stdout.splitlines() if line.strip() and " " not in line.strip()]
        if resolved.returncode != 0 or not modules:
            attempts.append({
                "address": candidate.get("address"),
                "status": "no-existing-module",
                "modalias": modalias,
                "detail": resolved.stdout.strip()[-500:],
            })
            continue
        for module in modules[:4]:
            loaded = _run([modprobe, module], timeout=15)
            attempts.append({
                "address": candidate.get("address"),
                "module": module,
                "status": "loaded" if loaded.returncode == 0 else "load-failed",
                "detail": loaded.stdout.strip()[-500:],
            })
            if loaded.returncode == 0:
                deadline = time.monotonic() + settle_seconds
                while time.monotonic() < deadline:
                    interfaces = wireless_interfaces()
                    if interfaces:
                        return {
                            "status": "recovered-existing-driver",
                            "interfaces": interfaces,
                            "candidates": candidates,
                            "attempts": attempts,
                            "kernel_messages": _kernel_messages(),
                        }
                    time.sleep(1)

    return {
        "status": "unresolved",
        "interfaces": wireless_interfaces(),
        "candidates": candidates,
        "attempts": attempts,
        "kernel_messages": _kernel_messages(),
        "next": "use exact vendor/device/modalias evidence; do not synthesize register behavior without a hardware contract",
    }
