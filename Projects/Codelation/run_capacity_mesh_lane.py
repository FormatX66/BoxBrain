from __future__ import annotations

import argparse
import json
import py_compile
import subprocess
import sys
import time
from pathlib import Path

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


def run_command(command: list[str]) -> tuple[int, float]:
    started = time.monotonic()
    completed = subprocess.run(command, cwd=ROOT.parents[1], check=False)
    return completed.returncode, time.monotonic() - started


def compile_python_tree() -> int:
    failures = 0
    for path in sorted(ROOT.rglob("*.py")):
        if any(part.startswith(".") for part in path.parts):
            continue
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError:
            failures += 1
    return 0 if failures == 0 else 1


def discover_test_modules() -> tuple[str, ...]:
    tests_root = ROOT / "tests"
    return tuple(
        f"Projects.Codelation.tests.{path.stem}"
        for path in sorted(tests_root.glob("test_*.py"))
    )


def suite_test_modules(suite: str) -> tuple[str, ...]:
    if suite == "core":
        return CORE_TEST_MODULES
    if suite == "broad":
        core = frozenset(CORE_TEST_MODULES)
        modules = tuple(
            module for module in discover_test_modules() if module not in core
        )
        if not modules:
            raise RuntimeError("broad suite has no tests independent of core")
        return modules
    if suite == "portability":
        return PORTABILITY_TEST_MODULES
    if suite == "verification":
        return ()
    raise ValueError(f"unsupported suite: {suite}")


def suite_command(suite: str) -> list[str] | None:
    if suite == "verification":
        return None
    return [
        sys.executable,
        "-m",
        "unittest",
        *suite_test_modules(suite),
        "-v",
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--posture", required=True, choices=("safe", "adventurous", "verify"))
    parser.add_argument("--suite", required=True, choices=("core", "broad", "verification", "portability"))
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()

    started = time.monotonic()
    if args.suite == "verification":
        returncode = compile_python_tree()
        duration = time.monotonic() - started
    else:
        command = suite_command(args.suite)
        assert command is not None
        returncode, duration = run_command(command)

    result = {
        "schema": "aurum-capacity-mesh-lane-result-v1",
        "name": args.name,
        "posture": args.posture,
        "suite": args.suite,
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
