#!/usr/bin/env python3
"""Unify local, peer, network and future capability sources into one Aurum field.

The mesh is deliberately transport-agnostic. It does not care whether a node
was discovered through sysfs, LAN discovery, a peer receipt, cellular relay or
another future carrier. It normalizes the evidence into capability nodes that
the autonomy planner can rank together.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Iterable

MESH_SCHEMA = "aurum.capability-mesh.v1"
DEFAULT_MESH = Path(os.environ.get("AURUM_CAPABILITY_MESH", "/run/aurum/capability-mesh.json"))


def _merge_node(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    merged["capabilities"] = sorted(
        set(existing.get("capabilities") or []) | set(incoming.get("capabilities") or [])
    )
    merged["confidence"] = max(
        float(existing.get("confidence") or 0.0), float(incoming.get("confidence") or 0.0)
    )

    properties = dict(existing.get("properties") or {})
    for key, value in (incoming.get("properties") or {}).items():
        if value not in (None, "", [], {}):
            if key == "evidence":
                prior = properties.get("evidence") or []
                properties["evidence"] = sorted(set(prior) | set(value if isinstance(value, list) else [value]))
            else:
                properties.setdefault(key, value)
    merged["properties"] = properties

    sources = set(existing.get("sources") or [existing.get("source")])
    sources.update(incoming.get("sources") or [incoming.get("source")])
    sources.discard(None)
    merged["sources"] = sorted(str(item) for item in sources)
    merged["source"] = merged["sources"][0] if len(merged["sources"]) == 1 else "capability-mesh"

    safety_rank = {"observe-only": 0, "bounded": 1, "guarded": 2, "deny": 3}
    current = str(existing.get("safety") or "observe-only")
    new = str(incoming.get("safety") or "observe-only")
    merged["safety"] = max((current, new), key=lambda item: safety_rank.get(item, 2))
    return merged


def build_mesh(
    local_graph: dict[str, Any] | None = None,
    *additional_sources: dict[str, Any],
) -> dict[str, Any]:
    """Merge any capability-bearing source documents into one graph."""
    source_documents: list[dict[str, Any]] = []
    if local_graph:
        source_documents.append(local_graph)
    source_documents.extend(item for item in additional_sources if item)

    nodes: dict[str, dict[str, Any]] = {}
    source_schemas: list[str] = []
    for document in source_documents:
        schema = document.get("schema")
        if schema:
            source_schemas.append(str(schema))
        for raw in document.get("nodes") or []:
            if not isinstance(raw, dict) or not raw.get("id"):
                continue
            node = dict(raw)
            node.setdefault("capabilities", [])
            node.setdefault("properties", {})
            node.setdefault("safety", "observe-only")
            node.setdefault("confidence", 0.5)
            node["sources"] = sorted(
                set(node.get("sources") or []) | ({str(node.get("source"))} if node.get("source") else set())
            )
            node_id = str(node["id"])
            if node_id in nodes:
                nodes[node_id] = _merge_node(nodes[node_id], node)
            else:
                nodes[node_id] = node

    by_capability: dict[str, list[str]] = {}
    by_scope: dict[str, list[str]] = {}
    for node_id, node in nodes.items():
        for capability in node.get("capabilities") or []:
            by_capability.setdefault(str(capability), []).append(node_id)

        properties = node.get("properties") or {}
        authorization = str(properties.get("authorization") or "").lower()
        if node.get("source") == "network-discovery" or "network-discovery" in (node.get("sources") or []):
            scope = "authorized-network" if authorization in {"authorized", "owned", "trusted"} else "unverified-network"
        elif node.get("source") in {"peer", "aurum-peer"} or any(
            item in {"peer", "aurum-peer"} for item in (node.get("sources") or [])
        ):
            scope = "authorized-peer" if authorization in {"authorized", "owned", "trusted"} else "unverified-peer"
        elif node.get("source") in {"cloud", "compute-cloud"} or any(
            item in {"cloud", "compute-cloud"} for item in (node.get("sources") or [])
        ):
            scope = "authorized-cloud" if authorization in {"authorized", "owned", "trusted"} else "unverified-cloud"
        else:
            scope = "local"
        node["properties"]["mesh_scope"] = scope
        by_scope.setdefault(scope, []).append(node_id)

    for mapping in (by_capability, by_scope):
        for values in mapping.values():
            values.sort()

    return {
        "schema": MESH_SCHEMA,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "read_only": True,
        "node_count": len(nodes),
        "source_schemas": sorted(set(source_schemas)),
        "nodes": [nodes[key] for key in sorted(nodes)],
        "index": {
            "by_capability": dict(sorted(by_capability.items())),
            "by_scope": dict(sorted(by_scope.items())),
        },
        "principle": "all authorized capability points participate in one field regardless of carrier",
    }


def load_sources(paths: Iterable[Path]) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            documents.append(payload)
    return documents


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Aurum unified capability mesh")
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, default=DEFAULT_MESH)
    args = parser.parse_args()

    sources = load_sources(args.sources)
    if not sources:
        raise SystemExit("no readable capability sources")
    mesh = build_mesh(sources[0], *sources[1:])
    _atomic_json(args.out, mesh)
    print(json.dumps(mesh, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
