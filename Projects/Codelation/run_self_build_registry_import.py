#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIELD_DIR = ROOT / "field"
sys.path.insert(0, str(FIELD_DIR))

from self_build_gap_spec import analyze_gap_support, learning_delta_score_spec  # noqa: E402
from self_build_registry import VERIFIED, registry_field  # noqa: E402
from self_build_registry_import import (  # noqa: E402
    register_verified_candidates,
    substrate_test_evidence_records,
)
from self_build_substrate_proposals import reason_substrate_proposals  # noqa: E402


def main() -> int:
    evidence_path = ROOT / "autobuild" / "self_build_substrate_test_evidence.json"
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    analysis = analyze_gap_support(learning_delta_score_spec())
    proposals = reason_substrate_proposals(analysis)
    records = substrate_test_evidence_records(payload)
    registry = register_verified_candidates(proposals, records)
    field = registry_field(registry)
    artifacts = registry.artifacts()
    output = {
        "ok": (
            len(artifacts) == 2
            and all(item.state == VERIFIED for item in artifacts)
            and not field.missing_refs()
        ),
        "states": {item.capability: item.state for item in artifacts},
        "variants": {
            item.capability: item.local_variant_identity for item in artifacts
        },
        "field_id": field.hex_id,
        "promoted_count": sum(1 for item in artifacts if item.state == "promoted"),
        "shared_binary": False,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if output["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
