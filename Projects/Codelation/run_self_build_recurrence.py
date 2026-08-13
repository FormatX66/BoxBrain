#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

FIELD_DIR = Path(__file__).resolve().parent / "field"
sys.path.insert(0, str(FIELD_DIR))

from self_build_proof import run_first_self_build_proof  # noqa: E402
from self_build_recurrence import continue_self_build, recurrence_field  # noqa: E402


def main() -> int:
    proof = run_first_self_build_proof()
    continuation = continue_self_build(proof)
    field = recurrence_field(continuation)
    payload = {
        "ok": (
            proof.candidate_sha256 == proof.promoted_sha256
            and proof.stages[-1] == "next-gap-emitted"
            and bool(continuation.ready_stages)
            and not continuation.federation.unassigned_lanes
            and not field.missing_refs()
        ),
        "completed_gap": proof.gap_name,
        "next_gap": continuation.next_gap,
        "source_completion_id": continuation.source_completion_id,
        "continuation_handoff_id": continuation.continuation_handoff_id,
        "ready_stages": list(continuation.ready_stages),
        "active_resources": list(continuation.federation.active_resources),
        "unassigned_lanes": list(continuation.federation.unassigned_lanes),
        "missing_capabilities": sorted(continuation.federation.missing_capabilities),
        "field_id": field.hex_id,
        "timer_dependency": False,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
