#!/usr/bin/env python3
"""ComputeWeave deterministic distributed-compute proof harness.

ComputeWeave treats compute as a capability field rather than a property of one
machine. This harness provides the first evidence protocol for proving that a
workload can be split across independent authorized workers, merged back into
one deterministic result, and compared with a single-node baseline.

The workload is intentionally synthetic and side-effect free. Physical and
remote workers can later implement the same shard receipt schema without
changing the fan-out/fan-in proof contract.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Iterable

BASELINE_SCHEMA = "aurum.computeweave-baseline.v1"
SHARD_SCHEMA = "aurum.computeweave-shard.v1"
PROOF_SCHEMA = "aurum.computeweave-proof.v1"


def unit_digest(seed: str, index: int, rounds: int) -> str:
    """Deterministic CPU work unit with no external state."""
    payload = f"{seed}:{index}".encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    for counter in range(rounds):
        digest = hashlib.sha256(digest + counter.to_bytes(8, "little")).digest()
    return digest.hex()


def select_indices(units: int, shard_index: int = 0, shard_count: int = 1) -> range:
    if units < 0:
        raise ValueError("units must be non-negative")
    if shard_count < 1:
        raise ValueError("shard_count must be positive")
    if not 0 <= shard_index < shard_count:
        raise ValueError("shard_index must be within shard_count")
    return range(shard_index, units, shard_count)


def run_items(
    *,
    seed: str,
    units: int,
    rounds: int,
    shard_index: int = 0,
    shard_count: int = 1,
) -> tuple[list[dict[str, Any]], float]:
    started = time.perf_counter()
    items = [
        {"index": index, "digest": unit_digest(seed, index, rounds)}
        for index in select_indices(units, shard_index, shard_count)
    ]
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return items, elapsed_ms


def root_digest(items: Iterable[dict[str, Any]]) -> str:
    ordered = sorted(items, key=lambda item: int(item["index"]))
    h = hashlib.sha256()
    for item in ordered:
        index = int(item["index"])
        digest = str(item["digest"])
        h.update(index.to_bytes(8, "little"))
        h.update(bytes.fromhex(digest))
    return h.hexdigest()


def baseline(*, seed: str, units: int, rounds: int, node: str) -> dict[str, Any]:
    items, execution_ms = run_items(seed=seed, units=units, rounds=rounds)
    return {
        "schema": BASELINE_SCHEMA,
        "seed": seed,
        "units": units,
        "rounds": rounds,
        "node": node,
        "item_count": len(items),
        "root_digest": root_digest(items),
        "execution_ms": round(execution_ms, 3),
        "verified": True,
    }


def shard(
    *,
    seed: str,
    units: int,
    rounds: int,
    shard_index: int,
    shard_count: int,
    node: str,
) -> dict[str, Any]:
    items, execution_ms = run_items(
        seed=seed,
        units=units,
        rounds=rounds,
        shard_index=shard_index,
        shard_count=shard_count,
    )
    return {
        "schema": SHARD_SCHEMA,
        "seed": seed,
        "units": units,
        "rounds": rounds,
        "node": node,
        "shard_index": shard_index,
        "shard_count": shard_count,
        "item_count": len(items),
        "items": items,
        "execution_ms": round(execution_ms, 3),
        "verified": True,
    }


def merge(baseline_receipt: dict[str, Any], shard_receipts: Iterable[dict[str, Any]]) -> dict[str, Any]:
    receipts = list(shard_receipts)
    if baseline_receipt.get("schema") != BASELINE_SCHEMA:
        raise ValueError("unsupported baseline schema")
    if not receipts:
        raise ValueError("at least one shard receipt is required")

    seed = str(baseline_receipt["seed"])
    units = int(baseline_receipt["units"])
    rounds = int(baseline_receipt["rounds"])
    shard_count = int(receipts[0]["shard_count"])
    by_index: dict[int, dict[str, Any]] = {}
    observed_shards: set[int] = set()

    for receipt in receipts:
        if receipt.get("schema") != SHARD_SCHEMA:
            raise ValueError("unsupported shard schema")
        if str(receipt.get("seed")) != seed or int(receipt.get("units")) != units or int(receipt.get("rounds")) != rounds:
            raise ValueError("shard workload identity mismatch")
        if int(receipt.get("shard_count")) != shard_count:
            raise ValueError("shard count mismatch")
        shard_index = int(receipt["shard_index"])
        if shard_index in observed_shards:
            raise ValueError(f"duplicate shard receipt: {shard_index}")
        observed_shards.add(shard_index)
        for item in receipt.get("items") or []:
            index = int(item["index"])
            if index in by_index:
                raise ValueError(f"duplicate work item: {index}")
            if index % shard_count != shard_index:
                raise ValueError(f"work item {index} returned by wrong shard")
            by_index[index] = {"index": index, "digest": str(item["digest"])}

    missing_shards = sorted(set(range(shard_count)) - observed_shards)
    missing_items = sorted(set(range(units)) - set(by_index))
    merged_root = root_digest(by_index.values())
    baseline_root = str(baseline_receipt["root_digest"])
    equivalent = not missing_shards and not missing_items and merged_root == baseline_root

    durations = [float(receipt.get("execution_ms") or 0.0) for receipt in receipts]
    distributed_execution_ms = max(durations) if durations else 0.0
    aggregate_worker_ms = sum(durations)
    baseline_ms = float(baseline_receipt.get("execution_ms") or 0.0)
    speedup = baseline_ms / distributed_execution_ms if distributed_execution_ms > 0 else 0.0

    return {
        "schema": PROOF_SCHEMA,
        "seed": seed,
        "units": units,
        "rounds": rounds,
        "baseline_node": baseline_receipt.get("node"),
        "worker_nodes": [receipt.get("node") for receipt in sorted(receipts, key=lambda item: int(item["shard_index"]))],
        "shard_count": shard_count,
        "missing_shards": missing_shards,
        "missing_items": missing_items,
        "baseline_root_digest": baseline_root,
        "merged_root_digest": merged_root,
        "equivalent_result": equivalent,
        "baseline_execution_ms": round(baseline_ms, 3),
        "distributed_execution_ms": round(distributed_execution_ms, 3),
        "aggregate_worker_ms": round(aggregate_worker_ms, 3),
        "execution_speedup": round(speedup, 3),
        "all_points_beat_one_point": bool(equivalent and speedup > 1.0),
        "verified": equivalent,
        "note": "execution speedup excludes scheduler/queue delay; queue timing should be recorded separately by orchestration receipts",
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object: {path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Aurum ComputeWeave proof harness")
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--seed", default="aurum-computeweave-v1")
    common.add_argument("--units", type=int, default=64)
    common.add_argument("--rounds", type=int, default=120000)
    common.add_argument("--node", required=True)
    common.add_argument("--out", type=Path, required=True)

    sub.add_parser("baseline", parents=[common])
    shard_parser = sub.add_parser("shard", parents=[common])
    shard_parser.add_argument("--shard-index", type=int, required=True)
    shard_parser.add_argument("--shard-count", type=int, required=True)

    merge_parser = sub.add_parser("merge")
    merge_parser.add_argument("--baseline", type=Path, required=True)
    merge_parser.add_argument("--shards", type=Path, required=True)
    merge_parser.add_argument("--out", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "baseline":
        payload = baseline(seed=args.seed, units=args.units, rounds=args.rounds, node=args.node)
        write_json(args.out, payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.command == "shard":
        payload = shard(
            seed=args.seed,
            units=args.units,
            rounds=args.rounds,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
            node=args.node,
        )
        write_json(args.out, payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    baseline_receipt = read_json(args.baseline)
    shard_receipts = [read_json(path) for path in sorted(args.shards.rglob("*.json"))]
    proof = merge(baseline_receipt, shard_receipts)
    write_json(args.out, proof)
    print(json.dumps(proof, indent=2, sort_keys=True))
    return 0 if proof["verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
