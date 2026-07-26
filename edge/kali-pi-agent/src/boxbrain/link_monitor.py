"""Detect target computers that explicitly authorized BoxBrain's SSH key."""

from __future__ import annotations

from datetime import datetime
import ipaddress
import json
import logging
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any

from boxbrain.diagnostics import (
    DIAGNOSTIC_AUTHORIZATION,
    DiagnosticError,
    TargetDiagnostics,
)
from boxbrain.links import load_links


LOG = logging.getLogger("boxbrain.link-monitor")
USB_INTERFACE = os.environ.get("BOXBRAIN_USB_INTERFACE", "usb0")
STATE_DIRECTORY = Path(os.environ.get("BOXBRAIN_STATE_DIR", "/var/lib/boxbrain"))
IDENTITY_FILE = Path(
    os.environ.get(
        "BOXBRAIN_TARGET_IDENTITY",
        "/var/lib/boxbrain/identity/target_ed25519",
    )
)
KNOWN_HOSTS_FILE = STATE_DIRECTORY / "identity" / "target_known_hosts"
LINKS_DIRECTORY = STATE_DIRECTORY / "links"
CHECK_INTERVAL = int(os.environ.get("BOXBRAIN_LINK_INTERVAL", "10"))
DIAGNOSTIC_INTERVAL = int(os.environ.get("BOXBRAIN_DIAGNOSTIC_INTERVAL", "900"))


def _run(command: list[str], timeout: int = 5) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def neighbor_candidates(interface: str = USB_INTERFACE) -> list[str]:
    result = _run(["ip", "-json", "neighbor", "show", "dev", interface])
    if result is None or result.returncode != 0:
        return []
    try:
        entries = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    candidates: list[str] = []
    for entry in entries:
        raw = entry.get("dst")
        state = set(entry.get("state", []))
        if not raw or state.intersection({"FAILED", "INCOMPLETE"}):
            continue
        try:
            address = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if address.version == 4 and (address.is_private or address.is_link_local):
            candidates.append(str(address))
    return sorted(set(candidates))


def probe(
    address: str,
    *,
    transport: str = "usb-ethernet-ssh",
    interface: str = USB_INTERFACE,
) -> dict[str, Any] | None:
    base_command = [
        "ssh",
        "-i",
        str(IDENTITY_FILE),
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=3",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        f"UserKnownHostsFile={KNOWN_HOSTS_FILE}",
        f"boxbrain-link@{address}",
    ]
    result = _run([*base_command, "hostname"], timeout=6)
    if result is None or result.returncode != 0:
        return None
    hostname_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not hostname_lines:
        return None

    platform = "unknown"
    linux_probe = _run([*base_command, "uname -srm"], timeout=6)
    if linux_probe is not None and linux_probe.returncode == 0:
        platform = linux_probe.stdout.strip() or platform
    else:
        windows_probe = _run([*base_command, "cmd.exe /c ver"], timeout=6)
        if windows_probe is not None and windows_probe.returncode == 0:
            platform = windows_probe.stdout.strip() or "Windows"

    return {
        "address": address,
        "hostname": hostname_lines[0],
        "platform": platform,
        "user": "boxbrain-link",
        "transport": transport,
        "interface": interface,
        "last_seen": int(time.time()),
        "last_checked": datetime_now(),
        "status": "connected",
    }


def save_link(link: dict[str, Any]) -> dict[str, Any]:
    LINKS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    destination = LINKS_DIRECTORY / f"{link['address'].replace('.', '-')}.json"
    merged: dict[str, Any] = {}
    try:
        existing = json.loads(destination.read_text(encoding="utf-8"))
        if isinstance(existing, dict):
            merged.update(existing)
    except (OSError, UnicodeError, json.JSONDecodeError):
        pass
    merged.update(link)
    handle, temporary_name = tempfile.mkstemp(
        prefix=".link-",
        suffix=".json",
        dir=LINKS_DIRECTORY,
        text=True,
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(merged, stream, separators=(",", ":"), sort_keys=True)
            stream.write("\n")
        os.replace(temporary_name, destination)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
    return merged


def _diagnostic_due(link: dict[str, Any]) -> bool:
    diagnostic = link.get("diagnostics")
    if not isinstance(diagnostic, dict):
        return True
    last_run = diagnostic.get("last_run")
    if not isinstance(last_run, str):
        return True
    try:
        timestamp = datetime.fromisoformat(last_run.replace("Z", "+00:00")).timestamp()
    except (ValueError, OverflowError):
        return True
    return time.time() - timestamp >= max(60, DIAGNOSTIC_INTERVAL)


def run_once() -> int:
    connected = 0
    if not IDENTITY_FILE.is_file():
        LOG.warning("Target SSH identity is missing: %s", IDENTITY_FILE)
        return connected
    diagnostics = TargetDiagnostics(str(STATE_DIRECTORY), str(IDENTITY_FILE))
    registered = {
        str(item.get("address")): item
        for item in load_links(str(STATE_DIRECTORY))
        if isinstance(item.get("address"), str)
    }
    candidates: dict[str, tuple[str, str]] = {
        address: ("usb-ethernet-ssh", USB_INTERFACE)
        for address in neighbor_candidates()
    }
    for address, existing in registered.items():
        transport = existing.get("transport")
        interface = existing.get("interface")
        if (
            transport == "network-ssh"
            and isinstance(interface, str)
            and interface
        ):
            candidates[address] = (transport, interface)

    for address, (transport, interface) in candidates.items():
        link = probe(address, transport=transport, interface=interface)
        if link is None:
            previous = registered.get(address)
            if previous is not None:
                previous.update(
                    {
                        "last_checked": datetime_now(),
                        "status": "offline",
                    }
                )
                save_link(previous)
            continue

        saved_link = save_link(link)
        connected += 1
        if _diagnostic_due(saved_link):
            try:
                diagnostics.diagnose(address, DIAGNOSTIC_AUTHORIZATION)
                LOG.info("Completed read-only diagnostics for %s", address)
            except DiagnosticError as error:
                saved_link["diagnostics"] = {
                    "status": "failed",
                    "last_run": datetime_now(),
                    "error": str(error)[:500],
                }
                save_link(saved_link)
                LOG.warning("Diagnostics failed for %s: %s", address, error)
    return connected


def datetime_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("BOXBRAIN_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    while True:
        try:
            count = run_once()
            if count:
                LOG.info("Confirmed %d authorized target link(s)", count)
        except Exception:
            LOG.exception("Target link check failed")
        time.sleep(max(5, CHECK_INTERVAL))


if __name__ == "__main__":
    main()
