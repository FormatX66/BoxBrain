#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

CODELATION_DIR = Path(__file__).resolve().parents[1]
FIELD_DIR = CODELATION_DIR / "field"
sys.path.insert(0, str(FIELD_DIR))
sys.path.insert(0, str(CODELATION_DIR))

from native_gap_catalog import CATALOG_REVISION, native_semantic_gap_names  # noqa: E402
from local_capability_verification import LOCAL_VERIFICATION_REVISION  # noqa: E402
from native_program_synthesis import SYNTHESIS_REVISION  # noqa: E402
from native_self_debug import SELF_DEBUG_REVISION  # noqa: E402
from run_native_autonomous_chain import STATE_SCHEMA  # noqa: E402

FARM_SCHEMA = "aurum-self-build-farm-v1"
DEFAULT_ARCHITECTURES = ("aarch64", "x86_64")


class FarmConvergenceError(RuntimeError):
    """Raised when a lane is missing, invalid, or architecture-dependent."""


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _load_lane(path: Path, *, start_gap: str) -> dict[str, Any]:
    try:
        lane = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FarmConvergenceError(f"lane is unreadable: {path}: {exc}") from exc
    if not isinstance(lane, dict):
        raise FarmConvergenceError(f"lane is not a JSON object: {path}")

    expected = {
        "schema": STATE_SCHEMA,
        "catalog_revision": CATALOG_REVISION,
        "synthesis_revision": SYNTHESIS_REVISION,
        "self_debug_revision": SELF_DEBUG_REVISION,
        "local_verification_revision": LOCAL_VERIFICATION_REVISION,
        "start_gap": start_gap,
    }
    for key, value in expected.items():
        if lane.get(key) != value:
            raise FarmConvergenceError(
                f"lane contract mismatch: {path}: {key}={lane.get(key)!r}, expected {value!r}"
            )

    generations = lane.get("generations")
    completed = lane.get("completed_generations")
    if not isinstance(generations, list) or not isinstance(completed, int) or completed < 1:
        raise FarmConvergenceError(f"lane has no completed generation: {path}")
    if len(generations) != completed:
        raise FarmConvergenceError(f"lane generation count mismatch: {path}")
    if lane.get("reasoning_required"):
        raise FarmConvergenceError(f"lane reached an unhandled reasoning boundary: {path}")
    return lane


def converge_lanes(
    input_root: Path,
    *,
    expected_gaps: Iterable[str],
    architectures: Iterable[str] = DEFAULT_ARCHITECTURES,
) -> dict[str, Any]:
    gaps = tuple(sorted(set(expected_gaps)))
    arches = tuple(sorted(set(architectures)))
    if not gaps or len(arches) < 2:
        raise FarmConvergenceError("farm convergence needs gaps and at least two architectures")

    results: list[dict[str, Any]] = []
    for gap in gaps:
        lane_by_arch: dict[str, dict[str, Any]] = {}
        digest_by_arch: dict[str, str] = {}
        for arch in arches:
            path = input_root / arch / f"{gap}.json"
            if not path.is_file():
                raise FarmConvergenceError(f"required lane is missing: {path}")
            lane = _load_lane(path, start_gap=gap)
            lane_by_arch[arch] = lane
            digest_by_arch[arch] = hashlib.sha256(_canonical_json(lane)).hexdigest()

        reference_arch = arches[0]
        for arch in arches[1:]:
            if lane_by_arch[arch] != lane_by_arch[reference_arch]:
                raise FarmConvergenceError(
                    f"cross-architecture self-build divergence: gap={gap} {reference_arch}!={arch}"
                )

        lane = lane_by_arch[reference_arch]
        results.append(
            {
                "start_gap": gap,
                "completed_generations": lane["completed_generations"],
                "latest_completed_gap": lane.get("latest_completed_gap"),
                "next_gap": lane.get("next_gap"),
                "blocked_reason": lane.get("blocked_reason"),
                "state_sha256": digest_by_arch[reference_arch],
                "architecture_digests": digest_by_arch,
            }
        )

    return {
        "schema": FARM_SCHEMA,
        "architectures": list(arches),
        "gap_count": len(gaps),
        "lane_count": len(gaps) * len(arches),
        "cross_architecture_determinism": "verified",
        "results": results,
    }


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Converge deterministic Aurum self-build farm lanes")
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = converge_lanes(
        args.input_root.resolve(),
        expected_gaps=native_semantic_gap_names(),
    )
    _atomic_json(args.output.resolve(), manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
