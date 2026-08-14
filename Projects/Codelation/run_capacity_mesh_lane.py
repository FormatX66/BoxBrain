from __future__ import annotations

import argparse
import json
import py_compile
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


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


def suite_command(suite: str) -> list[str] | None:
    if suite == "core":
        return [
            sys.executable,
            "-m",
            "unittest",
            "Projects.Codelation.tests.test_capacity_mesh",
            "Projects.Codelation.tests.test_mesh_efficiency",
            "Projects.Codelation.tests.test_event_handoff",
            "Projects.Codelation.tests.test_local_capability_verification",
            "-v",
        ]
    if suite == "broad":
        return [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "Projects/Codelation/tests",
            "-p",
            "test_*.py",
            "-v",
        ]
    if suite == "portability":
        return [
            sys.executable,
            "-m",
            "unittest",
            "Projects.Codelation.tests.test_capacity_mesh",
            "Projects.Codelation.tests.test_mesh_efficiency",
            "-v",
        ]
    if suite == "verification":
        return None
    raise ValueError(f"unsupported suite: {suite}")


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
