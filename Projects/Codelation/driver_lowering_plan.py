"""Deterministic non-executable lowering plans for Aurum driver programs.

This stage binds already-verified abstract behavior to independently verified
register selectors and bit masks. It deliberately emits descriptions only: no
MMIO/PIO addresses, callable hooks, device I/O, firmware operations, or physical
write authorization are produced here.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from Projects.Codelation.driver_program_synthesis import PROGRAM_SET_SCHEMA
from Projects.Codelation.driver_synthesis import MODEL_SCHEMA

LOWERING_PLAN_SCHEMA = "aurum.driver.lowering-plan.v0"
LOWERING_VERIFICATION_SCHEMA = "aurum.driver.lowering-verification.v0"
MAX_LOWERING_STEPS = 4096


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _identity(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _verified_binding(model: dict[str, Any], key: str) -> Any:
    if model.get("schema") != MODEL_SCHEMA:
        raise ValueError("binding model schema mismatch")
    claims = model.get("claims")
    if not isinstance(claims, dict):
        raise ValueError("binding model claims are missing")
    entry = claims.get(key)
    if not isinstance(entry, dict) or entry.get("state") != "verified":
        raise ValueError(f"required binding is not independently verified: {key}")
    if entry.get("value") is None:
        raise ValueError(f"verified binding has no value: {key}")
    return entry["value"]


def _no_bus_touch(kind: str, reason: str) -> dict[str, Any]:
    return {
        "abstract_action_kind": kind,
        "bus_touch": False,
        "classification": reason,
        "operation": None,
        "authorized": False,
    }


def _lower_action(action: dict[str, Any], binding_model: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(action, dict) or not isinstance(action.get("kind"), str) or not action["kind"]:
        raise ValueError("abstract action kind is required")
    kind = action["kind"]

    # These are environment/device-internal state changes, not software bus operations.
    if kind == "reset":
        return _no_bus_touch(kind, "external-lifecycle-event")
    if kind == "receive-character":
        return _no_bus_touch(kind, "external-input-event")
    if kind == "transfer-thr-to-shift":
        return _no_bus_touch(kind, "device-internal-transition")

    if kind == "read-receiver-buffer":
        selector = _verified_binding(binding_model, "selector.receiver_buffer")
        return {
            "abstract_action_kind": kind,
            "bus_touch": True,
            "classification": "register-read-plan",
            "operation": {
                "access": "read",
                "selector_binding": "selector.receiver_buffer",
                "selector": selector,
                "produces_runtime_operand": "received-byte",
            },
            "authorized": False,
        }

    if kind == "write-transmit-holding":
        selector = _verified_binding(binding_model, "selector.transmit_holding")
        return {
            "abstract_action_kind": kind,
            "bus_touch": True,
            "classification": "register-write-plan-only",
            "operation": {
                "access": "planned-write",
                "selector_binding": "selector.transmit_holding",
                "selector": selector,
                "requires_runtime_operand": "transmit-byte",
            },
            "authorized": False,
        }

    if kind == "set-dlab":
        if not isinstance(action.get("value"), bool):
            raise ValueError("set-dlab requires an explicit boolean value")
        selector = _verified_binding(binding_model, "selector.line_control")
        mask = _verified_binding(binding_model, "mask.line_control.dlab")
        if isinstance(mask, bool) or not isinstance(mask, int) or mask <= 0:
            raise ValueError("DLAB mask must be a positive integer")
        return {
            "abstract_action_kind": kind,
            "bus_touch": True,
            "classification": "register-read-modify-write-plan-only",
            "operation": {
                "access": "planned-read-modify-write",
                "selector_binding": "selector.line_control",
                "selector": selector,
                "mask_binding": "mask.line_control.dlab",
                "mask": mask,
                "desired_bit_set": action["value"],
            },
            "authorized": False,
        }

    # An unknown human label is never guessed into a hardware operation.
    raise ValueError(f"no verified lowering rule for abstract action: {kind}")


def synthesize_lowering_plan(
    program_set: dict[str, Any],
    binding_model: dict[str, Any],
) -> dict[str, Any]:
    """Bind abstract programs to verified selectors/masks without executing them."""

    if not isinstance(program_set, dict) or program_set.get("schema") != PROGRAM_SET_SCHEMA:
        raise ValueError("abstract driver program schema mismatch")
    if program_set.get("mode") != "abstract-non-actuating" or program_set.get("actuating") is not False:
        raise ValueError("only non-actuating abstract programs may be lowered")
    source_lowering = program_set.get("lowering")
    if not isinstance(source_lowering, dict) or source_lowering.get("performed") is not False:
        raise ValueError("source program set must not already be hardware-lowered")
    if source_lowering.get("physical_writes_authorized") is not False:
        raise ValueError("source program set authorizes physical writes")
    if binding_model.get("schema") != MODEL_SCHEMA:
        raise ValueError("binding model schema mismatch")
    if binding_model.get("actuating") is not False:
        raise ValueError("binding model must be non-actuating")

    programs = program_set.get("programs")
    if not isinstance(programs, list) or not programs:
        raise ValueError("abstract programs are required")

    lowered_programs: list[dict[str, Any]] = []
    total_steps = 0
    for program in programs:
        if not isinstance(program, dict) or program.get("actuating") is not False:
            raise ValueError("abstract program must be non-actuating")
        steps = program.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ValueError("abstract program steps are required")
        lowered_steps: list[dict[str, Any]] = []
        for index, step in enumerate(steps):
            total_steps += 1
            if total_steps > MAX_LOWERING_STEPS:
                raise ValueError("lowering plan exceeded step limit")
            if not isinstance(step, dict) or step.get("step") != index:
                raise ValueError("abstract program step order mismatch")
            action = step.get("abstract_action")
            lowering = _lower_action(action, binding_model)
            lowered_steps.append({
                "step": index,
                "transition_key": step.get("transition_key"),
                "abstract_action": action,
                "lowering": lowering,
            })
        lowered_programs.append({
            "source_program_identity": program.get("program_identity"),
            "mode": "non-executable-plan",
            "actuating": False,
            "steps": lowered_steps,
        })

    result = {
        "schema": LOWERING_PLAN_SCHEMA,
        "mode": "non-executable-plan",
        "actuating": False,
        "physical_hardware_proof": False,
        "source_program_set_identity": program_set.get("program_set_identity"),
        "source_transition_model_identity": program_set.get("model_identity"),
        "binding_model_identity": binding_model.get("model_identity"),
        "programs": lowered_programs,
        "safety": {
            "hardware_access_performed": False,
            "raw_register_addresses_emitted": False,
            "executable_hooks_emitted": False,
            "physical_writes_authorized": False,
            "firmware_changes_authorized": False,
            "plan_only_write_metadata": True,
        },
    }
    result["lowering_plan_identity"] = _identity(result)
    return result


def _contains_forbidden_execution_surface(value: Any) -> bool:
    """Reject common raw/executable surfaces even if manually injected into a plan."""

    forbidden_keys = {
        "address", "physical_address", "port_address", "mmio_address", "pio_address",
        "callable", "callback", "hook", "function", "executable", "device_path",
    }
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str) and key.lower() in forbidden_keys:
                return True
            if _contains_forbidden_execution_surface(child):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_execution_surface(child) for child in value)
    return False


def verify_lowering_plan(
    program_set: dict[str, Any],
    binding_model: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any]:
    """Verify that a lowering plan is exactly the deterministic safe projection."""

    if not isinstance(plan, dict) or plan.get("schema") != LOWERING_PLAN_SCHEMA:
        raise ValueError("lowering plan schema mismatch")
    if plan.get("mode") != "non-executable-plan" or plan.get("actuating") is not False:
        raise ValueError("lowering plan must be explicitly non-executable and non-actuating")
    if _contains_forbidden_execution_surface(plan):
        raise ValueError("lowering plan contains a raw or executable hardware surface")
    safety = plan.get("safety")
    if not isinstance(safety, dict):
        raise ValueError("lowering plan safety contract is missing")
    for key in (
        "hardware_access_performed",
        "raw_register_addresses_emitted",
        "executable_hooks_emitted",
        "physical_writes_authorized",
        "firmware_changes_authorized",
    ):
        if safety.get(key) is not False:
            raise ValueError(f"unsafe lowering plan safety flag: {key}")

    expected = synthesize_lowering_plan(program_set, binding_model)
    matched = _canonical(plan) == _canonical(expected)
    verification = {
        "schema": LOWERING_VERIFICATION_SCHEMA,
        "status": "passed" if matched else "failed",
        "actuating": False,
        "physical_hardware_proof": False,
        "source_program_set_identity": program_set.get("program_set_identity"),
        "binding_model_identity": binding_model.get("model_identity"),
        "lowering_plan_identity": plan.get("lowering_plan_identity"),
        "exact_deterministic_match": matched,
        "safety": {
            "hardware_access_performed": False,
            "physical_writes_authorized": False,
            "firmware_changes_authorized": False,
            "executable_driver_emitted": False,
        },
    }
    verification["verification_identity"] = _identity(verification)
    return verification
