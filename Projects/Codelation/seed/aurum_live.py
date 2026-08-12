#!/usr/bin/env python3
"""Minimal live Aurum graph and explicitly bounded peer heartbeat.

This module intentionally has no actuation surface. It records typed identity,
state, read-only capability and verification evidence nodes, then supports one
explicitly addressed heartbeat request. Network use is opt-in per invocation,
host-allowlisted, redirect-free and bounded by time/size limits.
"""

from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import platform
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA = "aurum.live.v1"
READ_ONLY_CAPABILITIES = (
    "system.identity.read",
    "system.state.read",
    "seed.summary.read",
    "evidence.verify.read",
    "peer.heartbeat.send",
)
FORBIDDEN_CAPABILITY_TERMS = ("exec", "shell", "write", "delete", "reboot", "actuate")
MAX_RESPONSE_BYTES = 4096


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _node_id(kind: str, name: str) -> str:
    digest = hashlib.blake2s(f"{kind}\0{name}".encode("utf-8"), digest_size=12).hexdigest()
    return f"{kind}:{digest}"


def _graph_digest(payload: dict[str, Any]) -> str:
    body = dict(payload)
    body.pop("digest", None)
    return hashlib.sha256(_canonical(body)).hexdigest()


def build_graph(
    *,
    node_name: str,
    hostname: str,
    python_version: str,
    architecture: str,
    install_path: str,
    seed_version: int,
) -> dict[str, Any]:
    identity_id = _node_id("identity", node_name)
    state_id = _node_id("state", f"{hostname}|{python_version}|{architecture}|{install_path}")
    nodes: list[dict[str, Any]] = [
        {
            "id": identity_id,
            "type": "identity",
            "name": node_name,
            "role": "Aurum seed on BBPI4",
            "seed_version": seed_version,
        },
        {
            "id": state_id,
            "type": "state",
            "facts": {
                "hostname": hostname,
                "python_version": python_version,
                "architecture": architecture,
                "install_path": install_path,
                "mode": "read-only-bootstrap",
            },
        },
    ]
    edges: list[dict[str, str]] = [{"from": identity_id, "rel": "HAS_STATE", "to": state_id}]

    for capability in READ_ONLY_CAPABILITIES:
        capability_id = _node_id("capability", capability)
        nodes.append(
            {
                "id": capability_id,
                "type": "capability",
                "name": capability,
                "authority": "read-only" if capability != "peer.heartbeat.send" else "bounded-outbound",
            }
        )
        edges.append({"from": identity_id, "rel": "SUPPORTS", "to": capability_id})

    graph = {
        "schema": SCHEMA,
        "created_unix": int(time.time()),
        "identity": identity_id,
        "nodes": nodes,
        "edges": edges,
        "heartbeat_sequence": 0,
        "last_heartbeat": None,
    }
    graph["digest"] = _graph_digest(graph)
    return graph


def verify_graph(graph: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if graph.get("schema") != SCHEMA:
        errors.append("schema")
    if graph.get("digest") != _graph_digest(graph):
        errors.append("digest")
    capabilities = [node.get("name", "") for node in graph.get("nodes", []) if node.get("type") == "capability"]
    if tuple(capabilities) != READ_ONLY_CAPABILITIES:
        errors.append("capabilities")
    lowered = " ".join(capabilities).lower()
    if any(term in lowered for term in FORBIDDEN_CAPABILITY_TERMS):
        errors.append("actuation-capability")
    if graph.get("identity") not in {node.get("id") for node in graph.get("nodes", [])}:
        errors.append("identity")
    return errors


def save_graph(path: Path, graph: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(_canonical(graph) + b"\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def load_graph(path: Path) -> dict[str, Any]:
    graph = json.loads(path.read_text(encoding="utf-8"))
    errors = verify_graph(graph)
    if errors:
        raise ValueError("invalid Aurum live graph: " + ",".join(errors))
    return graph


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        raise urllib.error.HTTPError(req.full_url, code, "redirect blocked", headers, fp)


def send_heartbeat(
    graph: dict[str, Any],
    *,
    peer_url: str,
    allow_host: str,
    timeout: float = 3.0,
    allow_http_loopback: bool = False,
) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(peer_url)
    if parsed.hostname != allow_host:
        raise ValueError("peer host is not explicitly allowlisted")
    if parsed.scheme != "https":
        loopback_ok = allow_http_loopback and parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        if not loopback_ok:
            raise ValueError("heartbeat requires HTTPS except explicit loopback verification")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("credentials/fragments are not allowed in peer URL")

    sequence = int(graph.get("heartbeat_sequence", 0)) + 1
    packet = {
        "schema": "aurum.heartbeat.v1",
        "identity": graph["identity"],
        "sequence": sequence,
        "graph_digest": graph["digest"],
        "capabilities": list(READ_ONLY_CAPABILITIES),
    }
    request = urllib.request.Request(
        peer_url,
        data=_canonical(packet),
        headers={"Content-Type": "application/json", "User-Agent": "Aurum/1"},
        method="POST",
    )
    opener = urllib.request.build_opener(_NoRedirect())
    with opener.open(request, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("peer response exceeded limit")
        status = int(getattr(response, "status", 0))
        if status < 200 or status >= 300:
            raise ValueError(f"peer status {status}")

    graph["heartbeat_sequence"] = sequence
    graph["last_heartbeat"] = {
        "sequence": sequence,
        "peer_host": parsed.hostname,
        "status": status,
        "response_sha256": hashlib.sha256(raw).hexdigest(),
    }
    graph["digest"] = _graph_digest(graph)
    return graph["last_heartbeat"]


@dataclass
class _LoopbackCapture:
    packet: dict[str, Any] | None = None


def loopback_self_test(graph: dict[str, Any]) -> dict[str, Any]:
    capture = _LoopbackCapture()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = min(int(self.headers.get("Content-Length", "0")), 8192)
            raw = self.rfile.read(length)
            capture.packet = json.loads(raw.decode("utf-8"))
            self.send_response(204)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        result = send_heartbeat(
            graph,
            peer_url=f"http://{host}:{port}/heartbeat",
            allow_host=str(host),
            timeout=2.0,
            allow_http_loopback=True,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)
    if capture.packet is None or capture.packet.get("graph_digest") is None:
        raise ValueError("loopback peer did not capture heartbeat")
    return result


def add_evidence(graph: dict[str, Any], *, name: str, result: str) -> None:
    evidence_id = _node_id("evidence", f"{name}|{result}")
    graph["nodes"].append({"id": evidence_id, "type": "evidence", "name": name, "result": result})
    graph["edges"].append({"from": graph["identity"], "rel": "VERIFIED_BY", "to": evidence_id})
    graph["digest"] = _graph_digest(graph)


def build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Aurum minimal live graph")
    commands = root.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    init.add_argument("--graph", type=Path, default=Path("aurum-live.json"))
    init.add_argument("--node-name", default="BBPI4/Aurum")
    init.add_argument("--hostname", default=socket.gethostname())
    init.add_argument("--python-version", default=platform.python_version())
    init.add_argument("--architecture", default=platform.machine())
    init.add_argument("--install-path", default="/opt/boxbrain/codelation")
    init.add_argument("--seed-version", type=int, default=1)

    verify = commands.add_parser("verify")
    verify.add_argument("--graph", type=Path, default=Path("aurum-live.json"))

    heartbeat = commands.add_parser("heartbeat")
    heartbeat.add_argument("--graph", type=Path, default=Path("aurum-live.json"))
    heartbeat.add_argument("--peer-url", required=True)
    heartbeat.add_argument("--allow-host", required=True)

    peer_test = commands.add_parser("peer-self-test")
    peer_test.add_argument("--graph", type=Path, default=Path("aurum-live.json"))
    return root


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "init":
        graph = build_graph(
            node_name=args.node_name,
            hostname=args.hostname,
            python_version=args.python_version,
            architecture=args.architecture,
            install_path=args.install_path,
            seed_version=args.seed_version,
        )
        add_evidence(graph, name="live-graph-init", result="passed")
        save_graph(args.graph, graph)
        print(f"AURUM_LIVE_INITIALIZED identity={graph['identity']} digest={graph['digest'][:16]}")
        return 0

    graph = load_graph(args.graph)
    if args.command == "verify":
        print(
            f"AURUM_LIVE_VERIFIED identity={graph['identity']} nodes={len(graph['nodes'])} "
            f"edges={len(graph['edges'])} heartbeat_sequence={graph['heartbeat_sequence']}"
        )
        return 0
    if args.command == "heartbeat":
        result = send_heartbeat(graph, peer_url=args.peer_url, allow_host=args.allow_host)
        save_graph(args.graph, graph)
        print(f"AURUM_HEARTBEAT_OK sequence={result['sequence']} peer={result['peer_host']} status={result['status']}")
        return 0
    result = loopback_self_test(graph)
    add_evidence(graph, name="loopback-heartbeat", result="passed")
    save_graph(args.graph, graph)
    print(f"AURUM_PEER_SELF_TEST_OK sequence={result['sequence']} status={result['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
