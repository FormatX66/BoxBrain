"""Safety policy for active BoxBrain assessments."""

from __future__ import annotations

import ipaddress
import json
import subprocess
from typing import Iterable


AUTHORIZATION_ASSERTION = "I am authorized to assess this network"
MAX_TARGET_ADDRESSES = 1024

_ALLOWED_RANGES = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
)


class PolicyError(ValueError):
    """Raised when an assessment request is outside the safety policy."""


def connected_ipv4_networks() -> list[ipaddress.IPv4Network]:
    try:
        completed = subprocess.run(
            ["ip", "-json", "-4", "address", "show", "up"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
        payload = json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return []

    networks: list[ipaddress.IPv4Network] = []
    for interface in payload:
        if interface.get("ifname") == "lo":
            continue
        for address in interface.get("addr_info", []):
            local = address.get("local")
            prefix = address.get("prefixlen")
            if address.get("family") != "inet" or local is None or prefix is None:
                continue
            try:
                networks.append(ipaddress.ip_network(f"{local}/{prefix}", strict=False))
            except ValueError:
                continue
    return networks


def validate_target(
    raw_target: str,
    authorization: str,
    connected: Iterable[ipaddress.IPv4Network] | None = None,
) -> ipaddress.IPv4Network:
    if authorization != AUTHORIZATION_ASSERTION:
        raise PolicyError("Explicit authorization assertion is required.")

    try:
        target = ipaddress.ip_network(raw_target, strict=False)
    except ValueError as error:
        raise PolicyError(f"Invalid IPv4 target: {raw_target}") from error

    if not isinstance(target, ipaddress.IPv4Network):
        raise PolicyError("Only IPv4 targets are supported in this release.")
    if not any(target.subnet_of(allowed) for allowed in _ALLOWED_RANGES):
        raise PolicyError("Target must be private or IPv4 link-local.")
    if target.num_addresses > MAX_TARGET_ADDRESSES:
        raise PolicyError(
            f"Target is too large; maximum scope is {MAX_TARGET_ADDRESSES} addresses."
        )

    local_networks = list(connected if connected is not None else connected_ipv4_networks())
    if not local_networks:
        raise PolicyError("No active non-loopback IPv4 network is available.")
    if not any(target.overlaps(local) for local in local_networks):
        raise PolicyError("Target must overlap a network directly connected to this probe.")

    return target
