#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

FIELD_DIR = Path(__file__).resolve().parent / "field"
sys.path.insert(0, str(FIELD_DIR))

from field_native_registry_bridge import build_verified_native_registry_artifact  # noqa: E402
from field_native_self_build import first_native_gap  # noqa: E402


def main() -> int:
    built = build_verified_native_registry_artifact(
        first_native_gap(),
        invocation_arguments={"text": "SLUSH Field field Aurum slush"},
        node="aurum-native-build-cell",
    )
    payload = {
        "ok": built.artifact.state == "verified",
        "artifact_identity": built.artifact_identity,
        "capability": built.artifact.capability,
        "state": built.artifact.state,
        "local_variant_identity": built.artifact.local_variant_identity,
        "carrier_sha256": built.artifact.carrier_sha256,
        "carrier_field_id": built.carrier.field_id,
        "program_identity": built.carrier.program_identity,
        "tape_identity": built.carrier.tape_identity,
        "verification_identity": built.verification_identity,
        "invocation_output": built.invocation_output,
        "carrier_bytes": len(built.carrier.carrier),
        "promotion_performed": False,
        "carrier_bytes_emitted": False,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
