#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

FIELD_DIR = Path(__file__).resolve().parent / "field"
sys.path.insert(0, str(FIELD_DIR))

from field_native_registry_bridge import build_verified_native_registry_artifact  # noqa: E402
from field_native_self_build import NativeGap  # noqa: E402
from native_gap_catalog import CATALOG_REVISION, get_native_semantic_gap  # noqa: E402
from native_program_synthesis import SYNTHESIS_REVISION, synthesize_native_expression  # noqa: E402


STATE_PATH = Path(__file__).resolve().parent / "autobuild" / "native_chain_state.json"
STATE_SCHEMA = "aurum-native-autonomous-chain-v0"


def run_chain(start_gap: str = "learning_delta_score", *, max_generations: int = 16) -> dict:
    current = start_gap
    generations: list[dict] = []
    blocked_reason: str | None = None

    for index in range(max_generations):
        spec = get_native_semantic_gap(current)
        if spec is None:
            blocked_reason = "semantic-spec-missing"
            break

        synthesis = synthesize_native_expression(
            spec.parameters,
            spec.examples,
            max_cost=spec.max_synthesis_cost,
        )
        if not synthesis.found or synthesis.expression is None:
            blocked_reason = "native-synthesis-not-found"
            generations.append(
                {
                    "generation": index + 1,
                    "gap": current,
                    "synthesis": asdict(synthesis),
                    "verified": False,
                }
            )
            break

        gap = NativeGap(
            name=spec.name,
            parameters=spec.parameters,
            expression=synthesis.expression,
            examples=spec.examples,
            purpose=spec.purpose,
            learned_principles=spec.principles,
            constraints=spec.constraints,
        )
        built = build_verified_native_registry_artifact(
            gap,
            invocation_arguments=spec.invocation_arguments,
            node="aurum-native-autonomous-chain",
        )
        if built.artifact.state != "verified":
            blocked_reason = "verified-registry-bridge-rejected"
            break

        generations.append(
            {
                "generation": index + 1,
                "gap": spec.name,
                "next_gap": spec.next_gap,
                "synthesis_proof_identity": synthesis.proof_identity,
                "synthesis_cost": synthesis.cost,
                "candidates_evaluated": synthesis.candidates_evaluated,
                "signatures_retained": synthesis.signatures_retained,
                "artifact_identity": built.artifact_identity,
                "local_variant_identity": built.artifact.local_variant_identity,
                "carrier_sha256": built.artifact.carrier_sha256,
                "carrier_field_id": built.carrier.field_id,
                "verification_identity": built.verification_identity,
                "invocation_output": built.invocation_output,
                "state": built.artifact.state,
                "promotion_performed": False,
                "model_reasoning_used": False,
                "source_generation_used": False,
                "filesystem_build_used": False,
                "subprocess_test_used": False,
            }
        )
        current = spec.next_gap
    else:
        blocked_reason = "generation-bound-reached"

    return {
        "schema": STATE_SCHEMA,
        "catalog_revision": CATALOG_REVISION,
        "synthesis_revision": SYNTHESIS_REVISION,
        "start_gap": start_gap,
        "completed_generations": len(generations),
        "latest_completed_gap": generations[-1]["gap"] if generations else None,
        "next_gap": current,
        "blocked_reason": blocked_reason,
        "reasoning_required": blocked_reason == "semantic-spec-missing",
        "reasoning_request": (
            {
                "gap": current,
                "required_output": "semantic contract plus bounded input-output examples; do not provide implementation",
                "shared_implementation": False,
            }
            if blocked_reason == "semantic-spec-missing"
            else None
        ),
        "timer_dependency": False,
        "generations": generations,
    }


def main() -> int:
    state = run_chain()
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(state, indent=2, sort_keys=True))
    # Reaching an unknown semantic gap is a normal safe stopping boundary, not failure.
    return 0 if state["completed_generations"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
