#!/usr/bin/env python3
"""Passive bootstrap seed for the Codelation experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import struct
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

MAGIC = b"CODESEED"
VERSION = 1
STATE_SIZE = 16
HEADER = struct.Struct(">8sB16sI")
EDGE = struct.Struct(">16s16sII")
ZERO_STATE = bytes(STATE_SIZE)


def state_id(observation: bytes) -> bytes:
    return hashlib.blake2s(observation, digest_size=STATE_SIZE).digest()


@dataclass
class EdgeScore:
    seen: int = 0
    confirmed: int = 0


@dataclass
class SeedGraph:
    last_state: bytes = ZERO_STATE
    edges: dict[tuple[bytes, bytes], EdgeScore] = field(default_factory=dict)

    def predict(self, source: bytes) -> bytes | None:
        candidates = [
            (score.confirmed, score.seen, target)
            for (edge_source, target), score in self.edges.items()
            if edge_source == source
        ]
        return max(candidates)[2] if candidates else None

    def observe(self, current: bytes) -> tuple[bytes | None, bool | None]:
        prediction = self.predict(self.last_state) if self.last_state != ZERO_STATE else None
        correct = prediction == current if prediction is not None else None
        if self.last_state != ZERO_STATE:
            edge = self.edges.setdefault((self.last_state, current), EdgeScore())
            edge.seen += 1
            if correct:
                edge.confirmed += 1
        self.last_state = current
        return prediction, correct

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("wb") as stream:
            stream.write(HEADER.pack(MAGIC, VERSION, self.last_state, len(self.edges)))
            for (source, target), score in sorted(self.edges.items()):
                stream.write(EDGE.pack(source, target, score.seen, score.confirmed))
        temporary.replace(path)

    @classmethod
    def load(cls, path: Path) -> "SeedGraph":
        if not path.exists():
            return cls()
        with path.open("rb") as stream:
            raw_header = stream.read(HEADER.size)
            if len(raw_header) != HEADER.size:
                raise ValueError("incomplete Codelation seed header")
            magic, version, last_state, edge_count = HEADER.unpack(raw_header)
            if magic != MAGIC or version != VERSION:
                raise ValueError("unsupported Codelation seed model")
            graph = cls(last_state=last_state)
            for _ in range(edge_count):
                raw_edge = stream.read(EDGE.size)
                if len(raw_edge) != EDGE.size:
                    raise ValueError("incomplete Codelation seed edge")
                source, target, seen, confirmed = EDGE.unpack(raw_edge)
                graph.edges[(source, target)] = EdgeScore(seen, confirmed)
            if stream.read(1):
                raise ValueError("unexpected data after Codelation seed model")
            return graph


def short(identity: bytes | None) -> str:
    return "none" if identity is None else identity.hex()[:12]


def _installed_wifi_bootstrap() -> None:
    """Use the installed Aurum TTY to recover/configure WiFi without a shell."""
    if not Path("/etc/aurum-installed.json").is_file():
        return
    aurum_root = Path("/opt/aurum")
    required = (
        aurum_root / "aurum_network.py",
        aurum_root / "aurum_wifi_recovery.py",
        aurum_root / "aurum_wifi_diag.py",
    )
    if not all(path.is_file() for path in required):
        print("AURUM_WIFI_BOOTSTRAP " + json.dumps({"status": "runtime-helper-missing"}, sort_keys=True))
        return
    root_text = str(aurum_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    try:
        from aurum_network import ensure_online, interactive_wifi_setup, wireless_interfaces
        from aurum_wifi_diag import diagnose
        from aurum_wifi_recovery import recover_existing_wifi_driver

        recovery = recover_existing_wifi_driver()
        interfaces = wireless_interfaces()
        if not interfaces:
            diagnostic = diagnose()
            compact = [
                {
                    "address": item.get("address"),
                    "vendor": item.get("vendor"),
                    "device": item.get("device"),
                    "class": item.get("class"),
                    "driver": item.get("driver"),
                    "modalias": item.get("modalias"),
                }
                for item in diagnostic.get("pci_network_candidates", [])
            ]
            print(
                "AURUM_WIFI_BOOTSTRAP "
                + json.dumps(
                    {
                        "status": "driver-unresolved",
                        "recovery": recovery,
                        "pci_candidates": compact,
                    },
                    sort_keys=True,
                )
            )
            return

        current = ensure_online(interactive=False)
        if current.get("online"):
            network = current
        else:
            old_in, old_out = sys.stdin, sys.stdout
            try:
                with Path("/dev/tty").open("r", encoding="utf-8", buffering=1) as tty_in, Path("/dev/tty").open(
                    "w", encoding="utf-8", buffering=1
                ) as tty_out:
                    sys.stdin = tty_in
                    sys.stdout = tty_out
                    network = interactive_wifi_setup(interfaces[0])
            finally:
                sys.stdin = old_in
                sys.stdout = old_out
        print(
            "AURUM_WIFI_BOOTSTRAP "
            + json.dumps(
                {
                    "status": "online" if network.get("online") else network.get("status"),
                    "interfaces": wireless_interfaces(),
                    "network": network,
                    "recovery": recovery,
                },
                sort_keys=True,
            )
        )
    except Exception as exc:
        print(
            "AURUM_WIFI_BOOTSTRAP "
            + json.dumps({"status": "failed", "detail": f"{type(exc).__name__}:{exc}"}, sort_keys=True)
        )


def _launch_installed_wifi_bootstrap() -> None:
    """Give the detached WiFi helper exclusive ownership of the physical TTY."""
    if not Path("/etc/aurum-installed.json").is_file():
        return
    parent_pid = os.getppid()
    try:
        script = str(Path(__file__).resolve())
        env = dict(os.environ)
        env["AURUM_WIFI_PARENT_PID"] = str(parent_pid)
        with Path("/dev/tty").open("r", encoding="utf-8", buffering=1) as tty_in, Path("/dev/tty").open(
            "w", encoding="utf-8", buffering=1
        ) as tty_out:
            subprocess.Popen(
                [sys.executable, script, "wifi-bootstrap"],
                stdin=tty_in,
                stdout=tty_out,
                stderr=tty_out,
                close_fds=True,
                env=env,
            )
        os.kill(parent_pid, signal.SIGSTOP)
        print("AURUM_WIFI_BOOTSTRAP " + json.dumps({"status": "launched-exclusive-tty"}, sort_keys=True))
    except Exception as exc:
        try:
            os.kill(parent_pid, signal.SIGCONT)
        except OSError:
            pass
        print(
            "AURUM_WIFI_BOOTSTRAP "
            + json.dumps({"status": "launch-failed", "detail": f"{type(exc).__name__}:{exc}"}, sort_keys=True)
        )


def build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Codelation passive state seed")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("observe", "predict"):
        command = commands.add_parser(name)
        command.add_argument("--model", type=Path, default=Path("seed.bin"))
        command.add_argument("observation")
    summary = commands.add_parser("summary")
    summary.add_argument("--model", type=Path, default=Path("seed.bin"))
    commands.add_parser("wifi-bootstrap")
    return root


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "wifi-bootstrap":
        parent_text = os.environ.get("AURUM_WIFI_PARENT_PID", "")
        parent_pid = int(parent_text) if parent_text.isdigit() else None
        try:
            time.sleep(0.5)
            _installed_wifi_bootstrap()
        finally:
            if parent_pid is not None:
                try:
                    os.kill(parent_pid, signal.SIGCONT)
                except OSError:
                    pass
        return 0

    graph = SeedGraph.load(args.model)
    if args.command == "observe":
        current = state_id(args.observation.encode())
        prediction, correct = graph.observe(current)
        graph.save(args.model)
        result = "unscored" if correct is None else ("confirmed" if correct else "missed")
        print(f"state={short(current)} prediction={short(prediction)} result={result}")
        if args.observation == "aurum-x86-ready":
            _launch_installed_wifi_bootstrap()
    elif args.command == "predict":
        source = state_id(args.observation.encode())
        print(f"source={short(source)} prediction={short(graph.predict(source))}")
    else:
        observations = sum(score.seen for score in graph.edges.values())
        confirmations = sum(score.confirmed for score in graph.edges.values())
        states = {state for edge in graph.edges for state in edge}
        print(
            f"version={VERSION} states={len(states)} edges={len(graph.edges)} "
            f"observations={observations} confirmations={confirmations} "
            f"last_state={short(graph.last_state)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
