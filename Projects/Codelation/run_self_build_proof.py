#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

FIELD_DIR = Path(__file__).resolve().parent / "field"
sys.path.insert(0, str(FIELD_DIR))

from self_build_proof import run_first_self_build_proof  # noqa: E402


def main() -> int:
    proof = run_first_self_build_proof()
    payload = asdict(proof)
    payload["ok"] = (
        proof.candidate_sha256 == proof.promoted_sha256
        and proof.stages[-1] == "next-gap-emitted"
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
