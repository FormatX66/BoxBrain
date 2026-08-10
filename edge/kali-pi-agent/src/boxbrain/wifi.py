"""Consent-gated Wi-Fi provisioning over the dedicated USB-C SSH link."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from typing import Any, TextIO


WIFI_PROVISION_AUTHORIZATION = "I am authorized to provision this Wi-Fi profile"
MAX_PAYLOAD_BYTES = 16 * 1024
_INTERFACE = re.compile(r"^[A-Za-z0-9_.:-]{1,32}$")


class WifiProvisionError(RuntimeError):
    """Raised when Wi-Fi provisioning cannot be completed safely."""


def _validate_ssid(ssid: str) -> str:
    value = ssid.strip()
    if not value or len(value.encode("utf-8")) > 32:
        raise WifiProvisionError("Choose a valid Wi-Fi network name.")
    if any(ord(character) < 32 for character in value):
        raise WifiProvisionError("The Wi-Fi network name is not supported.")
    return value


def _validate_passphrase(passphrase: str) -> str:
    if not passphrase:
        return ""
    is_raw_psk = len(passphrase) == 64 and all(
        character in "0123456789abcdefABCDEF" for character in passphrase
    )
    is_passphrase = (
        8 <= len(passphrase) <= 63
        and all(32 <= ord(character) <= 126 for character in passphrase)
    )
    if not (is_raw_psk or is_passphrase):
        raise WifiProvisionError("The Wi-Fi password must be 8 to 63 characters.")
    return passphrase


def _split_nmcli(line: str) -> list[str]:
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for character in line.rstrip("\r\n"):
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(character)
    if escaped:
        current.append("\\")
    fields.append("".join(current))
    return fields


def list_wifi_networks(
    *,
    interface: str = "wlan0",
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    """List visible Wi-Fi choices and saved profile names without credentials."""

    if not _INTERFACE.fullmatch(interface):
        raise WifiProvisionError("The Wi-Fi interface name is invalid.")
    if shutil.which("nmcli") is None:
        raise WifiProvisionError("NetworkManager is required for Wi-Fi selection.")
    environment = os.environ.copy()
    environment["LC_ALL"] = "C"
    visible = runner(
        [
            "nmcli", "-t", "-e", "yes", "-f", "IN-USE,SSID,SIGNAL,SECURITY",
            "device", "wifi", "list", "--rescan", "yes", "ifname", interface,
        ],
        capture_output=True,
        text=True,
        timeout=10,
        env=environment,
    )
    if visible.returncode != 0:
        raise WifiProvisionError("The Pi could not read nearby Wi-Fi networks.")
    saved = runner(
        ["nmcli", "-t", "-e", "yes", "-f", "NAME,TYPE", "connection", "show"],
        capture_output=True,
        text=True,
        timeout=10,
        env=environment,
    )
    saved_names = {
        values[0]
        for values in (_split_nmcli(line) for line in saved.stdout.splitlines())
        if saved.returncode == 0 and len(values) >= 2 and values[1] == "802-11-wireless"
    }
    networks: dict[str, dict[str, Any]] = {}
    current = ""
    for line in visible.stdout.splitlines():
        values = _split_nmcli(line)
        if len(values) < 4 or not values[1]:
            continue
        in_use, ssid, raw_signal, security = values[:4]
        try:
            signal = max(0, min(100, int(raw_signal)))
        except ValueError:
            signal = 0
        if in_use.strip() == "*":
            current = ssid
        candidate = {
            "ssid": ssid,
            "signal": signal,
            "security": security or "Open",
            "current": in_use.strip() == "*",
            "saved": ssid in saved_names,
        }
        previous = networks.get(ssid)
        if previous is not None:
            candidate["current"] = bool(previous.get("current")) or candidate["current"]
            candidate["saved"] = bool(previous.get("saved")) or candidate["saved"]
        if previous is None or signal > int(previous.get("signal", 0)):
            networks[ssid] = candidate
        elif candidate["current"] and not previous.get("current"):
            previous["current"] = True
    return {
        "interface": interface,
        "current_ssid": current,
        "networks": sorted(
            networks.values(),
            key=lambda item: (not item["current"], -int(item["signal"]), item["ssid"].casefold()),
        ),
        "saved_profiles": sorted(saved_names, key=str.casefold),
    }


def connect_wifi(
    ssid: str,
    passphrase: str,
    authorization: str,
    *,
    interface: str = "wlan0",
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    """Activate an operator-selected network without exposing its passphrase."""

    if authorization != WIFI_PROVISION_AUTHORIZATION:
        raise WifiProvisionError("Explicit Wi-Fi provisioning authorization is required.")
    if not _INTERFACE.fullmatch(interface):
        raise WifiProvisionError("The Wi-Fi interface name is invalid.")
    if shutil.which("nmcli") is None:
        raise WifiProvisionError("NetworkManager is required for Wi-Fi selection.")
    chosen_ssid = _validate_ssid(ssid)
    secret = _validate_passphrase(passphrase)
    command = [
        "nmcli", "--ask", "--wait", "45", "device", "wifi", "connect",
        chosen_ssid, "ifname", interface,
    ]
    if secret:
        profile_name = f"BoxBrain-{hashlib.sha256(chosen_ssid.encode('utf-8')).hexdigest()[:12]}"
        command.extend(["name", profile_name])
    else:
        profile_name = chosen_ssid
    environment = os.environ.copy()
    environment["LC_ALL"] = "C"
    os.umask(0o077)
    try:
        connected = runner(
            command,
            input=f"{secret}\n" if secret else "",
            capture_output=True,
            text=True,
            timeout=60,
            env=environment,
        )
    finally:
        secret = ""
        passphrase = ""
    if connected.returncode != 0:
        raise WifiProvisionError(
            "NetworkManager could not connect. Check the password or choose a saved network."
        )
    return {
        "status": "connected",
        "ssid": chosen_ssid,
        "interface": interface,
        "profile": profile_name,
        "credential_transport": "local-console-stdin",
        "credential_logged": False,
    }


def _validated_payload(stream: TextIO) -> tuple[str, str]:
    raw = stream.read(MAX_PAYLOAD_BYTES + 1)
    if len(raw.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise WifiProvisionError("The Wi-Fi provisioning payload is too large.")
    try:
        payload = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise WifiProvisionError("The Wi-Fi provisioning payload is invalid.") from error
    if not isinstance(payload, dict):
        raise WifiProvisionError("The Wi-Fi provisioning payload must be an object.")
    if payload.get("schema_version") != 1:
        raise WifiProvisionError("Unsupported Wi-Fi provisioning payload version.")
    if payload.get("source") != "windows-current-profile":
        raise WifiProvisionError("Wi-Fi provisioning requires the current Windows profile.")
    if payload.get("transport") != "usb-c-ssh":
        raise WifiProvisionError("Wi-Fi credentials are accepted only over USB-C SSH.")

    ssid = payload.get("ssid")
    passphrase = payload.get("passphrase")
    if not isinstance(ssid, str) or not ssid:
        raise WifiProvisionError("The current Wi-Fi SSID is missing.")
    ssid = _validate_ssid(ssid)
    if not isinstance(passphrase, str):
        raise WifiProvisionError("The current Wi-Fi passphrase is missing.")
    passphrase = _validate_passphrase(passphrase)
    if not passphrase:
        raise WifiProvisionError("The current Wi-Fi passphrase is missing.")
    return ssid, passphrase


def provision_current_wifi(
    stream: TextIO,
    authorization: str,
    *,
    interface: str = "wlan0",
    runner: Any = subprocess.run,
    effective_uid: int | None = None,
) -> dict[str, Any]:
    """Connect NetworkManager without placing the passphrase in argv or output."""

    if authorization != WIFI_PROVISION_AUTHORIZATION:
        raise WifiProvisionError("Explicit Wi-Fi provisioning authorization is required.")
    uid = os.geteuid() if effective_uid is None else effective_uid
    if uid != 0:
        raise WifiProvisionError("Wi-Fi provisioning must run as root.")
    if not _INTERFACE.fullmatch(interface):
        raise WifiProvisionError("The Wi-Fi interface name is invalid.")
    if shutil.which("nmcli") is None:
        raise WifiProvisionError("NetworkManager is required for Wi-Fi provisioning.")

    ssid, passphrase = _validated_payload(stream)
    profile_name = f"BoxBrain-USB-{hashlib.sha256(ssid.encode('utf-8')).hexdigest()[:12]}"
    environment = os.environ.copy()
    environment["LC_ALL"] = "C"
    os.umask(0o077)

    try:
        connected = runner(
            [
                "nmcli",
                "--ask",
                "--wait",
                "45",
                "device",
                "wifi",
                "connect",
                ssid,
                "ifname",
                interface,
                "name",
                profile_name,
            ],
            input=f"{passphrase}\n",
            capture_output=True,
            text=True,
            timeout=60,
            env=environment,
        )
    finally:
        passphrase = ""
    if connected.returncode != 0:
        raise WifiProvisionError(
            "NetworkManager could not connect using the authorized Windows profile."
        )

    state = runner(
        [
            "nmcli",
            "-g",
            "GENERAL.STATE,GENERAL.CONNECTION",
            "device",
            "show",
            interface,
        ],
        capture_output=True,
        text=True,
        timeout=10,
        env=environment,
    )
    if state.returncode != 0 or "connected" not in state.stdout.lower():
        raise WifiProvisionError("NetworkManager did not confirm the Wi-Fi connection.")

    return {
        "status": "connected",
        "ssid": ssid,
        "interface": interface,
        "profile": profile_name,
        "credential_transport": "usb-c-ssh-stdin",
        "credential_logged": False,
    }
