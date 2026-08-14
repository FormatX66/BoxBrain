#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

FIELD_DIR = Path(__file__).resolve().parent / "field"
sys.path.insert(0, str(FIELD_DIR))

from field_native_registry_bridge import build_verified_native_registry_artifact  # noqa: E402
from field_native_self_build import NativeGap  # noqa: E402
from native_gap_catalog import CATALOG_REVISION, get_native_semantic_gap  # noqa: E402
from native_program_synthesis import SYNTHESIS_REVISION, synthesize_native_expression  # noqa: E402


STATE_PATH = Path(__file__).resolve().parent / "autobuild" / "native_chain_state.json"
STATE_SCHEMA = "aurum-native-autonomous-chain-v2"


def run_chain(start_gap: str = "learning_delta_score", *, max_generations: int = 16) -> dict:
    current = start_gap
    completed: list[dict] = []
    failed_attempt: dict | None = None
    blocked_reason: str | None = None
    learned_expressions: dict[str, Mapping[str, Any]] = {}

    for _ in range(max_generations):
        spec = get_native_semantic_gap(current)
        if spec is None:
            blocked_reason = "semantic-spec-missing"
            break

        synthesis = synthesize_native_expression(
            spec.parameters,
            spec.examples,
            max_cost=spec.max_synthesis_cost,
            seed_expressions=learned_expressions,
        )
        if not synthesis.found or synthesis.expression is None:
            blocked_reason = "native-synthesis-not-found"
            failed_attempt = {
                "attempted_generation": len(completed) + 1,
                "gap": current,
                "synthesis": asdict(synthesis),
                "verified": False,
            }
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
            failed_attempt = {
                "attempted_generation": len(completed) + 1,
                "gap": current,
                "verified": False,
            }
            break

        # Only verified local capabilities become reusable synthesis primitives.
        learned_expressions[spec.name] = dict(synthesis.expression)
        completed.append(
            {
                "generation": len(completed) + 1,
                "gap": spec.name,
                "next_gap": spec.next_gap,
                "synthesis_proof_identity": synthesis.proof_identity,
                "synthesis_cost": synthesis.cost,
                "candidates_evaluated": synthesis.candidates_evaluated,
                "signatures_retained": synthesis.signatures_retained,
                "seed_expressions_considered": list(synthesis.seed_expressions_considered),
                "reusable_native_capabilities_after_build": sorted(learned_expressions),
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

    reasoning_required = blocked_reason in {"semantic-spec-missing", "native-synthesis-not-found"}
    return {
        "schema": STATE_SCHEMA,
        "catalog_revision": CATALOG_REVISION,
        "synthesis_revision": SYNTHESIS_REVISION,
        "start_gap": start_gap,
        "completed_generations": len(completed),
        "latest_completed_gap": completed[-1]["gap"] if completed else None,
        "next_gap": current,
        "blocked_reason": blocked_reason,
        "failed_attempt": failed_attempt,
        "reusable_native_capabilities": sorted(learned_expressions),
        "reasoning_required": reasoning_required,
        "reasoning_request": (
            {
                "gap": current,
                "reason": blocked_reason,
                "required_output": "semantic contract plus bounded input-output examples or a bounded builder-learning proposal; do not provide a promoted implementation",
                "shared_implementation": False,
            }
            if reasoning_required
            else None
        ),
        "timer_dependency": False,
        "generations": completed,
    }


def main() -> int:
    state = run_chain()
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(state, indent=2, sort_keys=True))
    # A real reasoning/build boundary is a normal safe stop when prior verified work exists.
    return 0 if state["completed_generations"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
