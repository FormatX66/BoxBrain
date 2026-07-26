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
    if len(ssid.encode("utf-8")) > 32 or any(ord(character) < 32 for character in ssid):
        raise WifiProvisionError("The current Wi-Fi SSID is not supported.")
    if not isinstance(passphrase, str):
        raise WifiProvisionError("The current Wi-Fi passphrase is missing.")
    is_raw_psk = len(passphrase) == 64 and all(
        character in "0123456789abcdefABCDEF" for character in passphrase
    )
    is_passphrase = (
        8 <= len(passphrase) <= 63
        and all(32 <= ord(character) <= 126 for character in passphrase)
    )
    if not (is_raw_psk or is_passphrase):
        raise WifiProvisionError("The current Wi-Fi passphrase format is not supported.")
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
