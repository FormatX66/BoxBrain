#!/usr/bin/env python3
"""Record and converge the four required Aurum virtual-lab proofs."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

PI3_DIR = Path(__file__).resolve().parents[1] / "AurumPi3"
sys.path.insert(0, str(PI3_DIR))

from aurum_release_gate import (  # noqa: E402
    GateValidationError,
    converge_evidence,
    evidence_document,
)


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateValidationError(f"could not read evidence {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise GateValidationError(f"evidence {path} must contain a JSON object")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("record")
    record.add_argument("--target", required=True)
    record.add_argument("--commit", required=True)
    record.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--commit", required=True)
    verify.add_argument("--output", type=Path, required=True)
    verify.add_argument("evidence", type=Path, nargs="+")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "record":
            value = evidence_document(args.target, args.commit)
            _write(args.output, value)
            print(f"AURUM_VIRTUAL_EVIDENCE_OK target={args.target} commit={value['commit']}")
            return 0
        value = converge_evidence((_read(path) for path in args.evidence), args.commit)
        _write(args.output, value)
        print(
            "AURUM_CONVERGENCE_GATE_OK "
            f"commit={value['commit']} "
            "qemu_pi3_evidence=virtual-machine-runtime "
            "physical_hardware_evidence=not-implied"
        )
        return 0
    except GateValidationError as exc:
        print(f"AURUM_CONVERGENCE_GATE_FAILED reason={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
