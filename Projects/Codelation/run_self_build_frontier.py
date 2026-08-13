#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

FIELD_DIR = Path(__file__).resolve().parent / "field"
sys.path.insert(0, str(FIELD_DIR))

from self_build_gap_spec import (  # noqa: E402
    analyze_gap_support,
    gap_analysis_field,
    learning_delta_score_spec,
)
from self_build_proof import run_first_self_build_proof  # noqa: E402
from self_build_recurrence import continue_self_build, recurrence_field  # noqa: E402
from self_build_substrate_growth import (  # noqa: E402
    plan_substrate_growth,
    substrate_growth_field,
)


def main() -> int:
    proof = run_first_self_build_proof()
    continuation = continue_self_build(proof)
    spec = learning_delta_score_spec()
    analysis = analyze_gap_support(spec)
    substrate = plan_substrate_growth(analysis)

    field = recurrence_field(continuation)
    field = field.merge(gap_analysis_field(spec, analysis))
    field = field.merge(substrate_growth_field(analysis, substrate))

    payload = {
        "ok": (
            proof.candidate_sha256 == proof.promoted_sha256
            and proof.stages[-1] == "next-gap-emitted"
            and proof.next_gap == spec.name
            and not field.missing_refs()
        ),
        "completed_gap": proof.gap_name,
        "next_gap": proof.next_gap,
        "recurrence_ready_stages": list(continuation.ready_stages),
        "recurrence_active_resources": list(continuation.federation.active_resources),
        "next_gap_directly_buildable": analysis.directly_buildable,
        "required_operations": sorted(analysis.required_operations),
        "supported_operations": sorted(analysis.supported_operations),
        "missing_operations": sorted(analysis.missing_operations),
        "substrate_gaps": list(substrate.substrate_gaps),
        "substrate_ready_stage": substrate.ready_stage,
        "substrate_active_resources": list(substrate.federation.active_resources),
        "substrate_unassigned": list(substrate.federation.unassigned_lanes),
        "field_id": field.hex_id,
        "timer_dependency": False,
        "promotion_scheduled": False,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
