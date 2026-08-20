from __future__ import annotations

import argparse
import json
import py_compile
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence, TypeVar

ROOT = Path(__file__).resolve().parent

CORE_TEST_MODULES = (
    "Projects.Codelation.tests.test_capacity_mesh",
    "Projects.Codelation.tests.test_mesh_efficiency",
    "Projects.Codelation.tests.test_event_handoff",
    "Projects.Codelation.tests.test_local_capability_verification",
)
PORTABILITY_TEST_MODULES = (
    "Projects.Codelation.tests.test_capacity_mesh",
    "Projects.Codelation.tests.test_mesh_efficiency",
)

T = TypeVar("T")


def _shard(items: Sequence[T], shard_index: int, shard_count: int) -> tuple[T, ...]:
    if shard_count < 1 or shard_index < 0 or shard_index >= shard_count:
        raise ValueError(f"invalid shard contract: {shard_index}/{shard_count}")
    return tuple(item for index, item in enumerate(items) if index % shard_count == shard_index)


def run_command(command: list[str]) -> tuple[int, float]:
    started = time.monotonic()
    completed = subprocess.run(command, cwd=ROOT.parents[1], check=False)
    return completed.returncode, time.monotonic() - started


def python_tree_paths() -> tuple[Path, ...]:
    return tuple(
        path
        for path in sorted(ROOT.rglob("*.py"))
        if not any(part.startswith(".") for part in path.parts)
    )


def compile_python_tree(*, shard_index: int = 0, shard_count: int = 1) -> tuple[int, int]:
    failures = 0
    paths = _shard(python_tree_paths(), shard_index, shard_count)
    for path in paths:
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError:
            failures += 1
    return (0 if failures == 0 else 1), len(paths)


def discover_test_modules() -> tuple[str, ...]:
    tests_root = ROOT / "tests"
    return tuple(
        f"Projects.Codelation.tests.{path.stem}"
        for path in sorted(tests_root.glob("test_*.py"))
    )


def full_suite_test_modules(suite: str) -> tuple[str, ...]:
    if suite == "core":
        return CORE_TEST_MODULES
    if suite == "broad":
        core = frozenset(CORE_TEST_MODULES)
        modules = tuple(module for module in discover_test_modules() if module not in core)
        if not modules:
            raise RuntimeError("broad suite has no tests independent of core")
        return modules
    if suite == "portability":
        return PORTABILITY_TEST_MODULES
    if suite == "verification":
        return tuple(str(path.relative_to(ROOT.parents[1])) for path in python_tree_paths())
    raise ValueError(f"unsupported suite: {suite}")


def suite_test_modules(suite: str, *, shard_index: int = 0, shard_count: int = 1) -> tuple[str, ...]:
    return _shard(full_suite_test_modules(suite), shard_index, shard_count)


def suite_command(suite: str, *, shard_index: int = 0, shard_count: int = 1) -> list[str] | None:
    if suite == "verification":
        return None
    modules = suite_test_modules(suite, shard_index=shard_index, shard_count=shard_count)
    if not modules:
        return []
    return [sys.executable, "-m", "unittest", *modules, "-v"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--posture", required=True, choices=("safe", "adventurous", "verify"))
    parser.add_argument("--suite", required=True, choices=("core", "broad", "verification", "portability"))
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()
    if args.shard_count < 1 or args.shard_index < 0 or args.shard_index >= args.shard_count:
        parser.error("invalid shard contract")

    started = time.monotonic()
    if args.suite == "verification":
        returncode, work_item_count = compile_python_tree(
            shard_index=args.shard_index,
            shard_count=args.shard_count,
        )
        duration = time.monotonic() - started
    else:
        command = suite_command(
            args.suite,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
        )
        assert command is not None
        modules = suite_test_modules(
            args.suite,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
        )
        work_item_count = len(modules)
        if command:
            returncode, duration = run_command(command)
        else:
            returncode = 0
            duration = time.monotonic() - started

    result = {
        "schema": "aurum-capacity-mesh-lane-result-v2",
        "name": args.name,
        "posture": args.posture,
        "suite": args.suite,
        "shard_index": args.shard_index,
        "shard_count": args.shard_count,
        "work_item_count": work_item_count,
        "verified": returncode == 0,
        "returncode": returncode,
        "duration_seconds": round(duration, 3),
    }
    print(json.dumps(result, sort_keys=True))
    if args.result is not None:
        args.result.parent.mkdir(parents=True, exist_ok=True)
        args.result.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
