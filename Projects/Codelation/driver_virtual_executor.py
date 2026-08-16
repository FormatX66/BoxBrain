"""Virtual-only executor for Aurum's non-executable driver lowering plans.

This module exercises lowered driver behavior against an in-memory logical
register bank. It has no OS/device I/O path and accepts no physical addresses,
ports, device files, MMIO/PIO handles, callbacks, or executable hooks. Writes
modify only a caller-provided Python dictionary.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from Projects.Codelation.driver_lowering_plan import LOWERING_PLAN_SCHEMA

VIRTUAL_EXECUTION_SCHEMA = "aurum.driver.virtual-execution.v0"
MAX_VIRTUAL_STEPS = 4096


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _identity(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _validate_plan_boundary(plan: dict[str, Any]) -> None:
    if not isinstance(plan, dict) or plan.get("schema") != LOWERING_PLAN_SCHEMA:
        raise ValueError("lowering plan schema mismatch")
    if plan.get("mode") != "non-executable-plan" or plan.get("actuating") is not False:
        raise ValueError("virtual executor accepts only non-executable non-actuating plans")
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


def _validate_byte(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255:
        raise ValueError(f"{name} must be an integer byte")
    return value


def execute_virtual_program(
    plan: dict[str, Any],
    source_program_identity: str,
    *,
    logical_registers: dict[str, int] | None = None,
    runtime_operands: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute one lowered program against a logical in-memory register bank only."""

    _validate_plan_boundary(plan)
    if not isinstance(source_program_identity, str) or not source_program_identity:
        raise ValueError("source program identity is required")
    if logical_registers is None:
        logical_registers = {}
    if runtime_operands is None:
        runtime_operands = {}
    if not isinstance(logical_registers, dict) or not isinstance(runtime_operands, dict):
        raise ValueError("logical registers and runtime operands must be objects")

    bank: dict[str, int] = {}
    for key, value in logical_registers.items():
        if not isinstance(key, str) or not key.startswith("selector."):
            raise ValueError("virtual register keys must be logical selector bindings")
        bank[key] = _validate_byte(value, key)

    programs = plan.get("programs")
    if not isinstance(programs, list):
        raise ValueError("lowering plan programs are missing")
    matches = [p for p in programs if isinstance(p, dict) and p.get("source_program_identity") == source_program_identity]
    if len(matches) != 1:
        raise ValueError("source program identity must resolve to exactly one lowered program")
    program = matches[0]
    if program.get("mode") != "non-executable-plan" or program.get("actuating") is not False:
        raise ValueError("lowered program is outside virtual-only boundary")
    steps = program.get("steps")
    if not isinstance(steps, list) or not steps or len(steps) > MAX_VIRTUAL_STEPS:
        raise ValueError("lowered program steps are invalid or unbounded")

    events: list[dict[str, Any]] = []
    outputs: dict[str, Any] = {}
    for index, step in enumerate(steps):
        if not isinstance(step, dict) or step.get("step") != index:
            raise ValueError("lowered program step order mismatch")
        lowering = step.get("lowering")
        if not isinstance(lowering, dict) or lowering.get("authorized") is not False:
            raise ValueError("lowered step is not explicitly plan-only")
        if lowering.get("bus_touch") is False:
            if lowering.get("operation") is not None:
                raise ValueError("no-bus-touch step unexpectedly contains an operation")
            events.append({
                "step": index,
                "transition_key": step.get("transition_key"),
                "kind": lowering.get("abstract_action_kind"),
                "virtual_effect": "none",
            })
            continue
        if lowering.get("bus_touch") is not True:
            raise ValueError("lowered step bus-touch classification is invalid")

        operation = lowering.get("operation")
        if not isinstance(operation, dict):
            raise ValueError("bus-touch plan step is missing operation metadata")
        access = operation.get("access")
        selector_binding = operation.get("selector_binding")
        if not isinstance(selector_binding, str) or not selector_binding.startswith("selector."):
            raise ValueError("operation lacks a logical selector binding")

        if access == "read":
            if selector_binding not in bank:
                raise ValueError(f"virtual register is not initialized: {selector_binding}")
            value = bank[selector_binding]
            output_name = operation.get("produces_runtime_operand")
            if not isinstance(output_name, str) or not output_name:
                raise ValueError("virtual read lacks output operand metadata")
            outputs[output_name] = value
            events.append({
                "step": index,
                "transition_key": step.get("transition_key"),
                "kind": lowering.get("abstract_action_kind"),
                "virtual_effect": "read",
                "selector_binding": selector_binding,
                "value": value,
            })
        elif access == "planned-write":
            operand_name = operation.get("requires_runtime_operand")
            if not isinstance(operand_name, str) or operand_name not in runtime_operands:
                raise ValueError("virtual planned write is missing its runtime operand")
            value = _validate_byte(runtime_operands[operand_name], operand_name)
            bank[selector_binding] = value
            events.append({
                "step": index,
                "transition_key": step.get("transition_key"),
                "kind": lowering.get("abstract_action_kind"),
                "virtual_effect": "write-in-memory-only",
                "selector_binding": selector_binding,
                "value": value,
            })
        elif access == "planned-read-modify-write":
            if selector_binding not in bank:
                raise ValueError(f"virtual register is not initialized: {selector_binding}")
            mask = operation.get("mask")
            if isinstance(mask, bool) or not isinstance(mask, int) or not 0 < mask <= 255:
                raise ValueError("virtual RMW mask must be a nonzero byte")
            desired = operation.get("desired_bit_set")
            if not isinstance(desired, bool):
                raise ValueError("virtual RMW desired bit state must be boolean")
            before = bank[selector_binding]
            after = (before | mask) if desired else (before & (~mask & 0xFF))
            bank[selector_binding] = after
            events.append({
                "step": index,
                "transition_key": step.get("transition_key"),
                "kind": lowering.get("abstract_action_kind"),
                "virtual_effect": "read-modify-write-in-memory-only",
                "selector_binding": selector_binding,
                "before": before,
                "after": after,
                "mask": mask,
            })
        else:
            raise ValueError(f"unsupported virtual plan access: {access}")

    result = {
        "schema": VIRTUAL_EXECUTION_SCHEMA,
        "mode": "in-memory-logical-registers-only",
        "actuating": False,
        "physical_hardware_proof": False,
        "source_lowering_plan_identity": plan.get("lowering_plan_identity"),
        "source_program_identity": source_program_identity,
        "initial_logical_registers": copy.deepcopy(logical_registers),
        "final_logical_registers": bank,
        "outputs": outputs,
        "events": events,
        "safety": {
            "hardware_access_performed": False,
            "os_device_io_performed": False,
            "physical_writes_performed": False,
            "firmware_changes_performed": False,
            "virtual_dictionary_writes_only": True,
        },
    }
    result["execution_identity"] = _identity(result)
    return result
