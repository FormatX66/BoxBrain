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
from local_capability_verification import (  # noqa: E402
    LOCAL_VERIFICATION_REVISION,
    verify_local_capability_for_gap,
)
from native_failure_diagnosis import diagnose_native_synthesis_failure  # noqa: E402
from native_gap_catalog import CATALOG_REVISION, get_native_semantic_gap  # noqa: E402
from native_program_synthesis import SYNTHESIS_REVISION, synthesize_native_expression  # noqa: E402
from native_self_debug import SELF_DEBUG_REVISION, audit_native_self_build  # noqa: E402


STATE_PATH = Path(__file__).resolve().parent / "autobuild" / "native_chain_state.json"
STATE_SCHEMA = "aurum-native-autonomous-chain-v5"


def _complete_local_candidates(diagnosis: Mapping[str, Any]) -> tuple[str, ...]:
    raw = diagnosis.get("local_capability_candidates", ())
    names: list[str] = []
    if isinstance(raw, (list, tuple)):
        for candidate in raw:
            if not isinstance(candidate, Mapping):
                continue
            if candidate.get("missing") or candidate.get("authority") != "none":
                continue
            name = str(candidate.get("name", ""))
            if name:
                names.append(name)
    return tuple(dict.fromkeys(names))


def _is_external_prerequisite_block(spec: Any, invocation_output: Any) -> bool:
    """Stop at verified fail-closed classification boundaries without inventing work.

    A blocked classification is evidence that the next action is not currently
    authorized/possible. It must not be treated as permission to advance into a
    live or otherwise unavailable semantic gap.
    """
    constraints = set(getattr(spec, "constraints", ()) or ())
    return (
        isinstance(invocation_output, str)
        and invocation_output.startswith("blocked-")
        and "classification-only" in constraints
        and "fail-closed" in constraints
    )


def run_chain(start_gap: str = "learning_delta_score", *, max_generations: int = 24) -> dict:
    current = start_gap
    completed: list[dict] = []
    failed_attempt: dict | None = None
    blocked_reason: str | None = None
    learned_expressions: dict[str, Mapping[str, Any]] = {}
    verified_local_capabilities: set[str] = set()

    for _ in range(max_generations):
        spec = get_native_semantic_gap(current)
        if spec is None:
            blocked_reason = "semantic-spec-missing"
            break

        preflight = audit_native_self_build(
            spec.parameters,
            spec.examples,
            stage="preflight",
        )
        if preflight.status == "blocked":
            blocked_reason = "self-debug-preflight-rejected"
            failed_attempt = {
                "attempted_generation": len(completed) + 1,
                "gap": current,
                "self_debug": asdict(preflight),
                "verified": False,
            }
            break

        synthesis = synthesize_native_expression(
            spec.parameters,
            spec.examples,
            max_cost=spec.max_synthesis_cost,
            seed_expressions=learned_expressions,
        )
        if not synthesis.found or synthesis.expression is None:
            diagnosis = diagnose_native_synthesis_failure(spec.parameters, spec.examples)
            self_debug = audit_native_self_build(
                spec.parameters,
                spec.examples,
                stage="post-failure",
                synthesis=asdict(synthesis),
                diagnosis=asdict(diagnosis),
            )

            # Internal deterministic continuation: if self-debug discovers a complete,
            # authority-free local candidate, verify that exact local implementation
            # against the unchanged semantic contract before escalating or stopping.
            if self_debug.internal_next_action == "verify-existing-local-capability":
                local_failures: list[dict[str, Any]] = []
                external_prerequisite_blocked = False
                for capability_name in _complete_local_candidates(asdict(diagnosis)):
                    try:
                        local = verify_local_capability_for_gap(spec, capability_name)
                    except (ImportError, AttributeError, TypeError, ValueError) as exc:
                        local_failures.append({"capability": capability_name, "error": str(exc)})
                        continue
                    if not local.verified:
                        local_failures.append(
                            {
                                "capability": capability_name,
                                "verification_identity": local.verification_identity,
                                "passed": local.passed,
                                "examples": local.examples,
                            }
                        )
                        continue

                    verified_local_capabilities.add(local.capability)
                    completed.append(
                        {
                            "generation": len(completed) + 1,
                            "gap": spec.name,
                            "next_gap": spec.next_gap,
                            "representation": "verified-local-capability-reuse",
                            "preflight_self_debug": {
                                "status": preflight.status,
                                "report_identity": preflight.report_identity,
                                "issues": len(preflight.issues),
                                "counterexamples": len(preflight.counterexamples),
                            },
                            "native_synthesis_found": False,
                            "native_synthesis_proof_identity": synthesis.proof_identity,
                            "native_candidates_evaluated": synthesis.candidates_evaluated,
                            "native_signatures_retained": synthesis.signatures_retained,
                            "post_failure_self_debug_identity": self_debug.report_identity,
                            "local_capability": local.capability,
                            "local_module": local.module,
                            "local_callable": local.callable_name,
                            "local_verification_adapter": local.adapter,
                            "local_implementation_sha256": local.implementation_sha256,
                            "verification_identity": local.verification_identity,
                            "invocation_output": local.invocation_output,
                            "state": "verified",
                            "authority_granted": local.authority_granted,
                            "routed_to_host": local.routed_to_host,
                            "promotion_performed": False,
                            "model_reasoning_used": False,
                            "source_generation_used": False,
                            "filesystem_build_used": False,
                            "subprocess_test_used": False,
                            "reusable_native_capabilities_after_build": sorted(learned_expressions),
                            "reusable_local_capabilities_after_build": sorted(verified_local_capabilities),
                        }
                    )
                    failed_attempt = None
                    if _is_external_prerequisite_block(spec, local.invocation_output):
                        # Keep current on the blocked classifier. A later event may retry
                        # after external evidence changes, but this event does not invent
                        # a successor implementation or treat absence as model work.
                        blocked_reason = "external-prerequisite-blocked"
                        external_prerequisite_blocked = True
                    else:
                        current = spec.next_gap
                        blocked_reason = None
                    break
                else:
                    blocked_reason = "local-capability-verification-failed"
                    failed_attempt = {
                        "attempted_generation": len(completed) + 1,
                        "gap": current,
                        "synthesis": asdict(synthesis),
                        "diagnosis": asdict(diagnosis),
                        "self_debug": asdict(self_debug),
                        "local_verification_failures": local_failures,
                        "verified": False,
                    }
                    break

                if external_prerequisite_blocked:
                    break

                # A local capability was verified and the gap advanced; continue in
                # this same event rather than waiting for another user/model prompt.
                continue

            blocked_reason = "native-synthesis-not-found"
            failed_attempt = {
                "attempted_generation": len(completed) + 1,
                "gap": current,
                "synthesis": asdict(synthesis),
                "diagnosis": asdict(diagnosis),
                "self_debug": asdict(self_debug),
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

        learned_expressions[spec.name] = dict(synthesis.expression)
        completed.append(
            {
                "generation": len(completed) + 1,
                "gap": spec.name,
                "next_gap": spec.next_gap,
                "representation": "field-native-program",
                "preflight_self_debug": {
                    "status": preflight.status,
                    "report_identity": preflight.report_identity,
                    "issues": len(preflight.issues),
                    "counterexamples": len(preflight.counterexamples),
                },
                "synthesis_proof_identity": synthesis.proof_identity,
                "synthesis_cost": synthesis.cost,
                "candidates_evaluated": synthesis.candidates_evaluated,
                "signatures_retained": synthesis.signatures_retained,
                "seed_expressions_considered": list(synthesis.seed_expressions_considered),
                "reusable_native_capabilities_after_build": sorted(learned_expressions),
                "reusable_local_capabilities_after_build": sorted(verified_local_capabilities),
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

    builder_learning: list[str] = []
    self_debug_payload: dict[str, Any] | None = None
    if failed_attempt is not None:
        diagnosis = failed_attempt.get("diagnosis")
        if isinstance(diagnosis, dict):
            raw = diagnosis.get("builder_learning", [])
            if isinstance(raw, (list, tuple)):
                builder_learning = [str(item) for item in raw]
        raw_self_debug = failed_attempt.get("self_debug")
        if isinstance(raw_self_debug, dict):
            self_debug_payload = raw_self_debug

    if blocked_reason == "semantic-spec-missing":
        reasoning_required = True
        internal_next_action = None
    elif self_debug_payload is not None:
        reasoning_required = bool(self_debug_payload.get("model_escalation_advised"))
        raw_action = self_debug_payload.get("internal_next_action")
        internal_next_action = str(raw_action) if raw_action else None
    else:
        reasoning_required = False
        internal_next_action = None

    return {
        "schema": STATE_SCHEMA,
        "catalog_revision": CATALOG_REVISION,
        "synthesis_revision": SYNTHESIS_REVISION,
        "self_debug_revision": SELF_DEBUG_REVISION,
        "local_verification_revision": LOCAL_VERIFICATION_REVISION,
        "start_gap": start_gap,
        "completed_generations": len(completed),
        "latest_completed_gap": completed[-1]["gap"] if completed else None,
        "next_gap": current,
        "blocked_reason": blocked_reason,
        "blocked_output": (
            completed[-1].get("invocation_output")
            if blocked_reason == "external-prerequisite-blocked" and completed
            else None
        ),
        "failed_attempt": failed_attempt,
        "reusable_native_capabilities": sorted(learned_expressions),
        "reusable_local_capabilities": sorted(verified_local_capabilities),
        "internal_next_action": internal_next_action,
        "reasoning_required": reasoning_required,
        "reasoning_request": (
            {
                "gap": current,
                "reason": blocked_reason,
                "required_output": "bounded diagnosis or builder-learning proposal only after Aurum self-debug has exhausted internal deterministic checks; do not provide a promoted implementation",
                "builder_learning": builder_learning,
                "self_debug_report_identity": (
                    self_debug_payload.get("report_identity") if self_debug_payload else None
                ),
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
    return 0 if state["completed_generations"] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
