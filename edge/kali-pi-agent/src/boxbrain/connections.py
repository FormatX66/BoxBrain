"""Bounded transport and capability inventory for the BoxBrain appliance."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any


Capability = dict[str, str]


def _capability(identifier: str, state: str, detail: str) -> Capability:
    return {"id": identifier, "state": state, "detail": detail}


def _interface_records(network: object) -> list[dict[str, Any]]:
    if not isinstance(network, dict):
        return []
    value = network.get("interfaces")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _interfaces(
    network: object,
    predicate: Callable[[str], bool],
) -> tuple[list[str], bool]:
    names: list[str] = []
    ready = False
    for item in _interface_records(network):
        name = item.get("name")
        if not isinstance(name, str) or not predicate(name):
            continue
        names.append(name[:32])
        addresses = item.get("addresses")
        if isinstance(addresses, list) and any(
            isinstance(address, str) and address for address in addresses
        ):
            ready = True
    return sorted(set(names)), ready


def _connected_links(
    links: object,
    predicate: Callable[[dict[str, Any]], bool],
) -> list[dict[str, Any]]:
    if not isinstance(links, list):
        return []
    return [
        item
        for item in links
        if isinstance(item, dict)
        and item.get("status") == "connected"
        and predicate(item)
    ]


def _network_capabilities(
    *,
    network_ready: bool,
    targets: list[dict[str, Any]],
    detail: str,
) -> list[Capability]:
    target_ready = bool(targets)
    windows_ready = any(
        str(item.get("platform", "")).lower().startswith("windows")
        for item in targets
    )
    return [
        _capability(
            "dashboard",
            "ready" if network_ready else "not-configured",
            detail,
        ),
        _capability(
            "ssh",
            "ready" if target_ready else "requires-authorization",
            "Key-only target link" if target_ready else "No authorized target link",
        ),
        _capability(
            "powershell",
            "bounded" if windows_ready else "not-configured",
            "Fixed diagnostic channel only" if windows_ready else "No Windows link",
        ),
        _capability(
            "cmd",
            "bounded" if windows_ready else "not-configured",
            "Fixed diagnostic channel only" if windows_ready else "No Windows link",
        ),
        _capability(
            "data",
            "ready" if network_ready else "not-configured",
            detail,
        ),
        _capability("video", "not-configured", "No video transport negotiated"),
        _capability("audio", "not-configured", "No audio transport negotiated"),
    ]


def build_connection_map(
    network: object,
    links: object,
    *,
    path_exists: Callable[[str], bool] | None = None,
    directory_has_entries: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    """Return observed transports without activating, pairing, or probing them."""

    exists = path_exists or (lambda value: Path(value).exists())
    has_entries = directory_has_entries or _directory_has_entries
    usb_interfaces, usb_network_ready = _interfaces(
        network,
        lambda name: name == "usb0" or name.startswith("usb"),
    )
    wifi_interfaces, wifi_ready = _interfaces(
        network,
        lambda name: name.startswith(("wlan", "wlp")),
    )
    ethernet_interfaces, ethernet_ready = _interfaces(
        network,
        lambda name: name.startswith(("eth", "en")),
    )
    bluetooth_interfaces, bluetooth_network_ready = _interfaces(
        network,
        lambda name: name.startswith(("bnep", "pan")),
    )

    usb_targets = _connected_links(
        links,
        lambda item: str(item.get("transport", "")).startswith("usb")
        or item.get("interface") == "usb0",
    )
    wifi_targets = _connected_links(
        links,
        lambda item: str(item.get("interface", "")).startswith(("wlan", "wlp")),
    )
    ethernet_targets = _connected_links(
        links,
        lambda item: str(item.get("interface", "")).startswith(("eth", "en")),
    )
    bluetooth_targets = _connected_links(
        links,
        lambda item: str(item.get("transport", "")).startswith("bluetooth")
        or str(item.get("interface", "")).startswith(("bnep", "pan")),
    )

    keyboard_ready = exists("/dev/hidg0")
    mouse_ready = exists("/dev/hidg1")
    usb_controller_available = has_entries("/sys/class/udc")
    bluetooth_available = has_entries("/sys/class/bluetooth")
    near_field_available = has_entries("/sys/class/nfc")

    usb_capabilities = _network_capabilities(
        network_ready=usb_network_ready,
        targets=usb_targets,
        detail="USB Ethernet / RNDIS",
    )
    usb_capabilities[1:1] = [
        _capability(
            "keyboard",
            "available" if keyboard_ready else "not-configured",
            "Explicit approval required before input",
        ),
        _capability(
            "mouse",
            "available" if mouse_ready else "not-configured",
            "Explicit approval required before input",
        ),
    ]

    transports = [
        {
            "id": "usb",
            "label": "USB / USB-C",
            "state": (
                "connected"
                if usb_network_ready or keyboard_ready or mouse_ready or usb_targets
                else "available" if usb_controller_available else "not-detected"
            ),
            "interfaces": usb_interfaces,
            "target_count": len(usb_targets),
            "capabilities": usb_capabilities,
        },
        {
            "id": "ethernet",
            "label": "Ethernet",
            "state": (
                "connected"
                if ethernet_ready
                else "available" if ethernet_interfaces else "not-detected"
            ),
            "interfaces": ethernet_interfaces,
            "target_count": len(ethernet_targets),
            "capabilities": _network_capabilities(
                network_ready=ethernet_ready,
                targets=ethernet_targets,
                detail="Private IPv4 over Ethernet",
            ),
        },
        {
            "id": "wifi",
            "label": "Wi-Fi",
            "state": (
                "connected"
                if wifi_ready
                else "available" if wifi_interfaces else "not-detected"
            ),
            "interfaces": wifi_interfaces,
            "target_count": len(wifi_targets),
            "capabilities": _network_capabilities(
                network_ready=wifi_ready,
                targets=wifi_targets,
                detail="Private IPv4 over Wi-Fi",
            ),
        },
        {
            "id": "bluetooth",
            "label": "Bluetooth",
            "state": (
                "connected"
                if bluetooth_network_ready or bluetooth_targets
                else "available" if bluetooth_available else "not-detected"
            ),
            "interfaces": bluetooth_interfaces,
            "target_count": len(bluetooth_targets),
            "capabilities": [
                _capability(
                    "dashboard",
                    "ready" if bluetooth_network_ready else "not-configured",
                    "Requires an explicitly configured Bluetooth PAN",
                ),
                _capability(
                    "keyboard",
                    "requires-pairing" if bluetooth_available else "not-configured",
                    "Separate Bluetooth HID trust boundary",
                ),
                _capability(
                    "mouse",
                    "requires-pairing" if bluetooth_available else "not-configured",
                    "Separate Bluetooth HID trust boundary",
                ),
                _capability(
                    "data",
                    "ready" if bluetooth_network_ready else "not-configured",
                    "Requires Bluetooth PAN or another approved profile",
                ),
                _capability("video", "not-configured", "No video profile enabled"),
                _capability("audio", "not-configured", "No audio profile enabled"),
            ],
        },
        {
            "id": "near-field",
            "label": "Near field / NFC",
            "state": "available" if near_field_available else "not-detected",
            "interfaces": [],
            "target_count": 0,
            "capabilities": [
                _capability(
                    "onboarding",
                    "available" if near_field_available else "not-configured",
                    "Identity or handoff only; not a repair-session carrier",
                ),
                _capability("dashboard", "unsupported", "Use the handed-off IP link"),
                _capability("keyboard", "unsupported", "NFC is not a HID session"),
                _capability("mouse", "unsupported", "NFC is not a HID session"),
                _capability(
                    "data",
                    "bounded" if near_field_available else "not-configured",
                    "Small onboarding records only",
                ),
                _capability("video", "unsupported", "Insufficient session transport"),
                _capability("audio", "unsupported", "Insufficient session transport"),
            ],
        },
    ]
    return {"schema_version": 1, "transports": transports}


def _directory_has_entries(value: str) -> bool:
    try:
        return any(Path(value).iterdir())
    except OSError:
        return False
