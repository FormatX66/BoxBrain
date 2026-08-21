#!/usr/bin/env python3
"""Passive bootstrap seed for the Codelation experiment."""

from __future__ import annotations

import argparse
import hashlib
import struct
from dataclasses import dataclass, field
from pathlib import Path

MAGIC = b"CODESEED"
VERSION = 1
STATE_SIZE = 16
HEADER = struct.Struct(">8sB16sI")
EDGE = struct.Struct(">16s16sII")
ZERO_STATE = bytes(STATE_SIZE)

HUMAN_TRAIT_SCHEMA = "aurum-human-traits-v1"
HUMAN_TRAIT_BUILD_POLICY = "all-traits-parallel; implementations-may-mature-in-stages"
HUMAN_TRAIT_IDS = (
    "TR8:WEB",
    "TR8:FILES",
    "TR8:MEDIA",
    "TR8:WRITE",
    "TR8:INTENT",
    "TR8:CONNECT",
    "TR8:RECOVER",
)


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


def build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Codelation passive state seed")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("observe", "predict"):
        command = commands.add_parser(name)
        command.add_argument("--model", type=Path, default=Path("seed.bin"))
        command.add_argument("observation")
    summary = commands.add_parser("summary")
    summary.add_argument("--model", type=Path, default=Path("seed.bin"))
    commands.add_parser("traits")
    return root


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "traits":
        print(
            f"schema={HUMAN_TRAIT_SCHEMA} required_on_every_seed=true "
            f"build_policy={HUMAN_TRAIT_BUILD_POLICY} traits={','.join(HUMAN_TRAIT_IDS)}"
        )
        return 0

    graph = SeedGraph.load(args.model)
    if args.command == "observe":
        current = state_id(args.observation.encode())
        prediction, correct = graph.observe(current)
        graph.save(args.model)
        result = "unscored" if correct is None else ("confirmed" if correct else "missed")
        print(f"state={short(current)} prediction={short(prediction)} result={result}")
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
