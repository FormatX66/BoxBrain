#!/usr/bin/env python3
"""Read-only physical/link topology reasoning for Aurum.

Connector shape is not treated as capability.  Endpoints advertise electrical/data
roles (USB host/device/dual-role, Ethernet, Wi-Fi, HDMI source/capture, etc.) and
this module composes only role-compatible links.  It never configures hardware.
"""
from __future__ import annotations

from typing import Any, Iterable

SCHEMA = "aurum.link-topology.v1"


def endpoint(node: str, name: str, medium: str, roles: Iterable[str], **properties: Any) -> dict[str, Any]:
    return {
        "id": f"{node}:{name}",
        "node": node,
        "name": name,
        "medium": medium,
        "roles": sorted(set(roles)),
        "properties": properties,
    }


def _usb_role_compatible(a: set[str], b: set[str]) -> bool:
    a_host = bool(a & {"host", "dual-role"})
    a_device = bool(a & {"device", "dual-role"})
    b_host = bool(b & {"host", "dual-role"})
    b_device = bool(b & {"device", "dual-role"})
    return (a_host and b_device) or (b_host and a_device)


def compatible(a: dict[str, Any], b: dict[str, Any]) -> tuple[bool, str]:
    if a.get("node") == b.get("node"):
        return False, "same-node"
    if a.get("medium") != b.get("medium"):
        return False, "different-medium"

    medium = str(a.get("medium"))
    ar = set(a.get("roles") or [])
    br = set(b.get("roles") or [])

    if medium == "usb":
        if not _usb_role_compatible(ar, br):
            return False, "usb-role-conflict"
        return True, "usb-host-device-compatible"

    if medium == "ethernet":
        return ("ethernet" in ar and "ethernet" in br), "ethernet-link"

    if medium == "wifi":
        if ("station" in ar and "ap" in br) or ("ap" in ar and "station" in br):
            return True, "wifi-ap-station"
        if "station" in ar and "station" in br:
            return True, "wifi-common-infrastructure-required"
        return False, "wifi-role-conflict"

    if medium == "hdmi":
        if ("source" in ar and "capture" in br) or ("capture" in ar and "source" in br):
            return True, "hdmi-source-capture"
        return False, "hdmi-role-conflict"

    return False, "unknown-medium"


def candidate_links(endpoints: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    items = list(endpoints)
    links: list[dict[str, Any]] = []
    for i, a in enumerate(items):
        for b in items[i + 1 :]:
            ok, reason = compatible(a, b)
            if not ok:
                continue
            links.append({
                "a": a["id"],
                "b": b["id"],
                "medium": a["medium"],
                "reason": reason,
                "read_only_reasoning": True,
            })
    return links


def score_topology(links: Iterable[dict[str, Any]], endpoints_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    links = list(links)
    media = {str(link.get("medium")) for link in links}
    connected_nodes: set[str] = set()
    independently_powered: set[str] = set()
    for link in links:
        for key in ("a", "b"):
            ep = endpoints_by_id.get(str(link.get(key))) or {}
            if ep.get("node"):
                connected_nodes.add(str(ep["node"]))
                if (ep.get("properties") or {}).get("node_independent_power"):
                    independently_powered.add(str(ep["node"]))
    return {
        "link_count": len(links),
        "medium_count": len(media),
        "media": sorted(media),
        "connected_nodes": sorted(connected_nodes),
        "independently_powered_nodes": sorted(independently_powered),
        "redundancy_score": len(media) + max(0, len(independently_powered) - 1),
    }


def pi4_hopper_main_reference() -> dict[str, Any]:
    """Reference capabilities for the current three-node experiment.

    This is a role model, not proof that any particular cable/link is currently active.
    """
    eps = [
        endpoint("pi4", "usb-c-otg", "usb", {"device", "dual-role"}, node_independent_power=True,
                 possible_functions=["usb-ethernet", "hid", "serial"]),
        endpoint("pi4", "usb-a3", "usb", {"host"}, node_independent_power=True),
        endpoint("pi4", "ethernet", "ethernet", {"ethernet"}, node_independent_power=True),
        endpoint("pi4", "wifi", "wifi", {"station", "ap"}, node_independent_power=True),
        endpoint("pi4", "hdmi-capture-usb", "hdmi", {"capture"}, node_independent_power=True),
        endpoint("hopper", "usb-c", "usb", {"host"}),
        endpoint("hopper", "ethernet", "ethernet", {"ethernet"}),
        endpoint("hopper", "wifi", "wifi", {"station"}),
        endpoint("hopper", "hdmi-out", "hdmi", {"source"}),
        endpoint("main", "usb-c", "usb", {"host"}),
        endpoint("main", "ethernet", "ethernet", {"ethernet"}),
        endpoint("main", "wifi", "wifi", {"station"}),
    ]
    links = candidate_links(eps)
    return {
        "schema": SCHEMA,
        "read_only": True,
        "endpoints": eps,
        "candidate_links": links,
        "score": score_topology(links, {item["id"]: item for item in eps}),
        "important_constraint": "Pi4 USB-A ports are host-only; direct host-to-host USB is not a valid data link.",
    }
