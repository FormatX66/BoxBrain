#!/usr/bin/env python3
"""Machine-readable codelation capability graph for Aurum.

This module is intentionally read-only. It translates observed hardware evidence
into machine-native capabilities and ranks candidate resources for an intent.
It does not execute the chosen path.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Iterable

from aurum_hardware import collect_hardware_profile

GRAPH_SCHEMA = "aurum.capability-graph.v1"
PLAN_SCHEMA = "aurum.capability-plan.v1"
DEFAULT_GRAPH = Path(os.environ.get("AURUM_CAPABILITY_GRAPH", "/run/aurum/capability-graph.json"))


def _read(path: Path, default: str | None = None) -> str | None:
    try:
        value = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return default
    return value or default


def _node(
    node_id: str,
    label: str,
    source: str,
    capabilities: Iterable[str],
    *,
    properties: dict[str, Any] | None = None,
    safety: str = "observe-only",
    confidence: float = 1.0,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "label": label,
        "source": source,
        "capabilities": sorted({str(value) for value in capabilities if value}),
        "properties": properties or {},
        "safety": safety,
        "confidence": round(max(0.0, min(1.0, confidence)), 3),
    }


def _power_wakeup(sys_path: Path) -> str | None:
    return _read(sys_path / "power" / "wakeup")


def _input_caps(name: str) -> set[str]:
    lower = name.lower()
    caps = {"sense"}
    if any(token in lower for token in ("mouse", "touchpad", "trackpad", "keyboard", "hid")):
        caps |= {"actuate", "recover"}
    return caps


def _net_caps(name: str) -> set[str]:
    caps = {"transport", "sense"}
    if name.startswith(("wl", "wlan")):
        caps.add("radio")
    if name.startswith(("en", "eth")):
        caps.add("electrical-link")
    return caps


def _block_caps(item: dict[str, Any]) -> set[str]:
    caps = {"store"}
    if item.get("removable"):
        caps |= {"transport", "recover"}
    return caps


def _pci_caps(item: dict[str, Any]) -> set[str]:
    device_class = str(item.get("class") or "").lower()
    caps = {"transport"}
    if device_class.startswith("0x03"):
        caps |= {"compute", "actuate"}
    elif device_class.startswith("0x04"):
        caps |= {"sense", "actuate"}
    elif device_class.startswith("0x02"):
        caps.add("sense")
    elif device_class.startswith("0x01"):
        caps.add("store")
    return caps


def _sysfs_extra_nodes(sys_root: Path) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []

    for entry in sorted((sys_root / "class" / "power_supply").glob("*")):
        nodes.append(
            _node(
                f"power:{entry.name}",
                entry.name,
                "sysfs:power_supply",
                {"power", "sense"},
                properties={
                    "type": _read(entry / "type", "power"),
                    "capacity_percent": _read(entry / "capacity"),
                    "status": _read(entry / "status"),
                    "present": _read(entry / "present"),
                },
            )
        )

    for entry in sorted((sys_root / "class" / "thermal").glob("thermal_zone*")):
        nodes.append(
            _node(
                f"thermal:{entry.name}",
                _read(entry / "type", entry.name) or entry.name,
                "sysfs:thermal",
                {"sense", "power"},
                properties={"temp_millic": _read(entry / "temp")},
            )
        )

    for entry in sorted((sys_root / "class" / "rtc").glob("rtc*")):
        nodes.append(
            _node(
                f"rtc:{entry.name}",
                entry.name,
                "sysfs:rtc",
                {"timing", "recover"},
                properties={"name": _read(entry / "name")},
            )
        )

    for entry in sorted((sys_root / "class" / "sound").glob("card*")):
        nodes.append(
            _node(
                f"sound:{entry.name}",
                entry.name,
                "sysfs:sound",
                {"sense", "actuate", "transport"},
                properties={"id": _read(entry / "id")},
                confidence=0.75,
            )
        )

    tpm_root = sys_root / "class" / "tpm"
    if tpm_root.exists():
        for entry in sorted(tpm_root.glob("tpm*")):
            nodes.append(
                _node(
                    f"trust:{entry.name}",
                    entry.name,
                    "sysfs:tpm",
                    {"trust", "store"},
                    safety="guarded",
                )
            )
    return nodes


def build_capability_graph(
    profile: dict[str, Any] | None = None,
    *,
    sys_root: Path = Path("/sys"),
    proc_root: Path = Path("/proc"),
) -> dict[str, Any]:
    profile = profile or collect_hardware_profile(sys_root=sys_root, proc_root=proc_root)
    nodes: list[dict[str, Any]] = []

    cpu = profile.get("cpu") or {}
    if cpu:
        nodes.append(
            _node(
                "cpu:0",
                str(cpu.get("model_name") or "CPU"),
                "profile:cpu",
                {"compute", "timing", "recover"},
                properties={
                    "logical_processors": cpu.get("logical_processors"),
                    "vendor": cpu.get("vendor"),
                },
            )
        )

    memory = profile.get("memory") or {}
    if memory.get("total_kib"):
        nodes.append(
            _node(
                "memory:ram",
                "Volatile system memory",
                "profile:memory",
                {"store"},
                properties={
                    "persistence": "volatile",
                    "capacity_kib": memory.get("total_kib"),
                    "latency_class": "low",
                },
            )
        )

    for item in profile.get("block_devices") or []:
        if item.get("partition"):
            continue
        name = str(item.get("name") or "block")
        nodes.append(
            _node(
                f"block:{name}",
                str(item.get("model") or name),
                "profile:block",
                _block_caps(item),
                properties={
                    "removable": bool(item.get("removable")),
                    "size_sectors": item.get("size_sectors"),
                    "driver": item.get("driver"),
                    "persistence": "persistent",
                },
            )
        )

    for item in profile.get("network_interfaces") or []:
        name = str(item.get("name") or "net")
        wake = _power_wakeup(sys_root / "class" / "net" / name / "device")
        caps = _net_caps(name)
        if wake == "enabled":
            caps.add("recover")
        nodes.append(
            _node(
                f"net:{name}",
                name,
                "profile:network",
                caps,
                properties={
                    "operstate": item.get("operstate"),
                    "carrier": item.get("carrier"),
                    "driver": item.get("driver"),
                    "wake": wake,
                },
            )
        )

    for item in profile.get("input_devices") or []:
        event = str(item.get("event") or "event")
        name = str(item.get("name") or event)
        wake = _power_wakeup(sys_root / "class" / "input" / event / "device")
        nodes.append(
            _node(
                f"input:{event}",
                name,
                "profile:input",
                _input_caps(name),
                properties={"driver": item.get("driver"), "wake": wake},
                confidence=0.9 if wake == "enabled" else 0.75,
            )
        )

    for item in profile.get("graphics_devices") or []:
        card = str(item.get("card") or "card")
        nodes.append(
            _node(
                f"gpu:{card}",
                card,
                "profile:graphics",
                {"compute", "actuate", "transport"},
                properties={"driver": item.get("driver"), "vendor": item.get("vendor")},
            )
        )

    for item in profile.get("usb_devices") or []:
        address = str(item.get("address") or "usb")
        name = str(item.get("product_name") or f"USB {address}")
        wake = _power_wakeup(sys_root / "bus" / "usb" / "devices" / address)
        caps = {"transport", "power"}
        lower = name.lower()
        if any(token in lower for token in ("mouse", "keyboard", "touch", "hid")):
            caps |= {"sense", "actuate", "recover"}
        elif any(token in lower for token in ("audio", "headset", "microphone", "speaker")):
            caps |= {"sense", "actuate"}
        nodes.append(
            _node(
                f"usb:{address}",
                name,
                "profile:usb",
                caps,
                properties={"driver": item.get("driver"), "wake": wake},
                confidence=0.9 if wake == "enabled" else 0.8,
            )
        )

    for item in profile.get("pci_devices") or []:
        address = str(item.get("address") or "pci")
        nodes.append(
            _node(
                f"pci:{address}",
                address,
                "profile:pci",
                _pci_caps(item),
                properties={
                    "class": item.get("class"),
                    "driver": item.get("driver"),
                    "vendor": item.get("vendor"),
                    "device": item.get("device"),
                },
                confidence=0.65,
            )
        )

    nodes.extend(_sysfs_extra_nodes(sys_root))

    unique: dict[str, dict[str, Any]] = {}
    for item in nodes:
        unique.setdefault(item["id"], item)

    by_capability: dict[str, list[str]] = {}
    for item in unique.values():
        for capability in item["capabilities"]:
            by_capability.setdefault(capability, []).append(item["id"])
    for ids in by_capability.values():
        ids.sort()

    return {
        "schema": GRAPH_SCHEMA,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_profile_schema": profile.get("schema"),
        "read_only": True,
        "node_count": len(unique),
        "nodes": list(unique.values()),
        "index": {"by_capability": dict(sorted(by_capability.items()))},
        "principle": "select by capability and desired state change, not conventional device name",
    }


def _quality_score(node: dict[str, Any], intent: dict[str, Any]) -> tuple[float, list[str]]:
    required = set(intent.get("requires") or [])
    preferred = set(intent.get("prefers") or [])
    avoided = set(intent.get("avoid") or [])
    caps = set(node.get("capabilities") or [])
    properties = node.get("properties") or {}
    reasons: list[str] = []

    missing = required - caps
    if missing:
        return -1.0, [f"missing:{','.join(sorted(missing))}"]

    score = 50.0 + 30.0 * float(node.get("confidence") or 0)
    for capability in sorted(required):
        reasons.append(f"has:{capability}")
    for capability in sorted(preferred & caps):
        score += 8.0
        reasons.append(f"preferred:{capability}")
    for capability in sorted(avoided & caps):
        score -= 25.0
        reasons.append(f"avoid:{capability}")

    if properties.get("wake") == "enabled":
        score += 12.0
        reasons.append("wake-enabled")
    if properties.get("operstate") == "up":
        score += 5.0
        reasons.append("active")
    if node.get("safety") == "guarded":
        score -= 10.0
        reasons.append("guarded")
    if node.get("safety") == "observe-only":
        reasons.append("bounded")

    return score, reasons


def plan_intent(graph: dict[str, Any], intent: dict[str, Any]) -> dict[str, Any]:
    ranked: list[dict[str, Any]] = []
    for node in graph.get("nodes") or []:
        score, reasons = _quality_score(node, intent)
        if score < 0:
            continue
        ranked.append(
            {
                "node_id": node["id"],
                "label": node.get("label"),
                "score": round(score, 2),
                "capabilities": node.get("capabilities"),
                "reasons": reasons,
                "execution_authorized": False,
            }
        )
    ranked.sort(key=lambda item: (-item["score"], item["node_id"]))
    return {
        "schema": PLAN_SCHEMA,
        "intent": intent,
        "candidate_count": len(ranked),
        "candidates": ranked,
        "selected": ranked[0] if ranked else None,
        "execution_authorized": False,
        "note": "planner is advisory/read-only; a separate bounded actuator must execute any path",
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Aurum codelation capability graph")
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture = subparsers.add_parser("capture")
    capture.add_argument("--out", type=Path, default=DEFAULT_GRAPH)

    query = subparsers.add_parser("plan")
    query.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    query.add_argument("--requires", nargs="+", required=True)
    query.add_argument("--prefers", nargs="*", default=[])
    query.add_argument("--avoid", nargs="*", default=[])

    args = parser.parse_args()

    if args.command == "capture":
        graph = build_capability_graph()
        _atomic_json(args.out, graph)
        print(json.dumps(graph, indent=2, sort_keys=True))
        return 0

    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    intent = {"requires": args.requires, "prefers": args.prefers, "avoid": args.avoid}
    plan = plan_intent(graph, intent)
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0 if plan.get("selected") else 2


if __name__ == "__main__":
    raise SystemExit(main())
