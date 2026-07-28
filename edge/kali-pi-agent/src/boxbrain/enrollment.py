"""Explicit enrollment for authorized targets reached over private-network SSH."""

from __future__ import annotations

import ipaddress
import json
import subprocess
from typing import Any

from boxbrain import link_monitor
from boxbrain.links import load_links


LINK_AUTHORIZATION = "I am authorized to link this computer"
NETWORK_SSH_TRANSPORT = "network-ssh"
SUPPORTED_TRANSPORTS = frozenset({NETWORK_SSH_TRANSPORT})
MAX_REGISTERED_TARGETS = 64
ALLOWED_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
)


class TargetEnrollmentError(RuntimeError):
    """Raised when a target cannot be safely enrolled."""


def _safe_address(raw: str) -> str:
    try:
        address = ipaddress.ip_address(raw)
    except ValueError as error:
        raise TargetEnrollmentError("Target must be an IPv4 address.") from error
    if address.version != 4 or not any(address in network for network in ALLOWED_NETWORKS):
        raise TargetEnrollmentError(
            "Target enrollment is restricted to RFC1918 or link-local IPv4 addresses."
        )
    return str(address)


def _route_interface(address: str) -> str:
    try:
        result = subprocess.run(
            ["ip", "-json", "route", "get", address],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise TargetEnrollmentError(
            "The Pi could not inspect the route to this target."
        ) from error
    if result.returncode != 0:
        raise TargetEnrollmentError(
            "The target is not reachable through a connected Pi network."
        )
    try:
        routes: Any = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise TargetEnrollmentError("The Pi returned an invalid route result.") from error
    if not isinstance(routes, list) or not routes or not isinstance(routes[0], dict):
        raise TargetEnrollmentError(
            "The target is not reachable through a connected Pi network."
        )
    interface = str(routes[0].get("dev", "")).strip()
    if not interface or interface == "lo":
        raise TargetEnrollmentError(
            "The target route must use a non-loopback Pi interface."
        )
    return interface


def enroll_target(
    address: str,
    transport: str,
    authorization: str,
) -> dict[str, Any]:
    if authorization != LINK_AUTHORIZATION:
        raise TargetEnrollmentError(
            "Explicit authorization is required before linking a target."
        )
    if transport not in SUPPORTED_TRANSPORTS:
        raise TargetEnrollmentError("Unsupported target transport.")

    safe_address = _safe_address(address)
    interface = _route_interface(safe_address)
    if interface == link_monitor.USB_INTERFACE:
        raise TargetEnrollmentError(
            "USB-C targets are enrolled automatically after target-side authorization."
        )
    if not link_monitor.IDENTITY_FILE.is_file():
        raise TargetEnrollmentError("The Pi target SSH identity is unavailable.")

    links = load_links(str(link_monitor.STATE_DIRECTORY))
    registered = {
        str(item.get("address"))
        for item in links
        if isinstance(item.get("address"), str)
    }
    if safe_address not in registered and len(registered) >= MAX_REGISTERED_TARGETS:
        raise TargetEnrollmentError("The target registry limit has been reached.")

    link = link_monitor.probe(
        safe_address,
        transport=transport,
        interface=interface,
    )
    if link is None:
        raise TargetEnrollmentError(
            "SSH verification failed. Run the BoxBrain onboarding script on the "
            "target, allow this Pi address, and confirm that port 22 is reachable."
        )
    link.update(
        {
            "enrollment": "explicit",
            "authorized_at": link_monitor.datetime_now(),
            "last_checked": link_monitor.datetime_now(),
        }
    )
    return link_monitor.save_link(link)
