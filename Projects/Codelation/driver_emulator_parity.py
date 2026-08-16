"""Differential parity verification between Aurum synthesis and a live QEMU UART.

Consumes live emulator-only observations plus independently reconciled bindings
and transitions. It never opens a host device or performs physical I/O.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from Projects.Codelation.driver_lowering_plan import synthesize_lowering_plan
from Projects.Codelation.driver_program_synthesis import synthesize_abstract_driver_programs
from Projects.Codelation.driver_qemu_uart_probe import PROBE_SCHEMA
from Projects.Codelation.driver_synthesis import EvidenceClaim, MODEL_SCHEMA, reconcile_evidence
from Projects.Codelation.driver_transition_synthesis import TRANSITION_MODEL_SCHEMA, TransitionClaim, reconcile_transition_evidence
from Projects.Codelation.driver_virtual_executor import execute_virtual_program

PARITY_SCHEMA = "aurum.driver.emulator-parity.v0"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _identity(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _verified_claim(model: dict[str, Any], key: str) -> Any:
    if model.get("schema") != MODEL_SCHEMA:
        raise ValueError("binding model schema mismatch")
    entry = model.get("claims", {}).get(key)
    if not isinstance(entry, dict) or entry.get("state") != "verified":
        raise ValueError(f"binding is not independently verified: {key}")
    return entry.get("value")


def _verified_transition(model: dict[str, Any], key: str) -> dict[str, Any]:
    if model.get("schema") != TRANSITION_MODEL_SCHEMA:
        raise ValueError("transition model schema mismatch")
    entry = model.get("transitions", {}).get(key)
    if not isinstance(entry, dict) or entry.get("state") != "verified":
        raise ValueError(f"transition is not independently verified: {key}")
    transition = entry.get("transition")
    if not isinstance(transition, dict):
        raise ValueError(f"verified transition has no body: {key}")
    return transition


def _observation(probe: dict[str, Any], name: str) -> dict[str, int]:
    item = probe.get("observations", {}).get(name)
    if not isinstance(item, dict):
        raise ValueError(f"probe observation is missing: {name}")
    port, value = item.get("port"), item.get("value")
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 0xFFFF:
        raise ValueError(f"probe observation port is invalid: {name}")
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFF:
        raise ValueError(f"probe observation byte is invalid: {name}")
    return {"port": port, "value": value}


def verify_emulator_parity(binding_model: dict[str, Any], transition_model: dict[str, Any], probe: dict[str, Any], *, virtual_dlab_execution: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(probe, dict) or probe.get("schema") != PROBE_SCHEMA:
        raise ValueError("emulator probe schema mismatch")
    if probe.get("origin") != "qemu-hmp-live" or probe.get("emulator_execution_observed") is not True:
        raise ValueError("parity requires a live QEMU HMP observation")
    if probe.get("physical_hardware_observation") is not False:
        raise ValueError("physical observations are outside this emulator parity lane")
    safety = probe.get("safety")
    if not isinstance(safety, dict):
        raise ValueError("emulator probe safety contract is missing")
    for key in ("host_physical_io_performed", "host_device_file_io_performed", "physical_writes_performed", "firmware_changes_performed"):
        if safety.get(key) is not False:
            raise ValueError(f"unsafe live probe flag: {key}")
    if safety.get("qemu_process_only") is not True:
        raise ValueError("probe is not constrained to the QEMU process")

    base_port = probe.get("base_port")
    if isinstance(base_port, bool) or not isinstance(base_port, int) or not 0 <= base_port <= 0xFFFF:
        raise ValueError("emulator base port is invalid")

    rb = _verified_claim(binding_model, "selector.receiver_buffer")
    thr = _verified_claim(binding_model, "selector.transmit_holding")
    ier = _verified_claim(binding_model, "selector.interrupt_enable")
    lcr = _verified_claim(binding_model, "selector.line_control")
    mcr = _verified_claim(binding_model, "selector.modem_control")
    lsr = _verified_claim(binding_model, "selector.line_status")
    dll = _verified_claim(binding_model, "selector.divisor_latch_lsb")
    dlm = _verified_claim(binding_model, "selector.divisor_latch_msb")
    dlab_mask = _verified_claim(binding_model, "mask.line_control.dlab")
    loop_mask = _verified_claim(binding_model, "mask.modem_control.loop")
    dr_mask = _verified_claim(binding_model, "mask.line_status.data_ready")
    thre_mask = _verified_claim(binding_model, "mask.line_status.thre")
    temt_mask = _verified_claim(binding_model, "mask.line_status.temt")

    offsets = probe.get("selector_offsets", {})
    data_offset = offsets.get("receiver_or_transmit_or_divisor_lsb", offsets.get("receiver_or_divisor_lsb"))
    selector_checks = {
        "data_or_divisor_lsb": rb.get("offset") == thr.get("offset") == dll.get("offset") == data_offset,
        "interrupt_or_divisor_msb": ier.get("offset") == dlm.get("offset") == offsets.get("interrupt_enable_or_divisor_msb"),
        "line_control": lcr.get("offset") == offsets.get("line_control"),
        "modem_control": mcr.get("offset") == offsets.get("modem_control", 4),
        "line_status": lsr.get("offset") == offsets.get("line_status"),
        "bank_requirements": rb.get("dlab") == 0 and thr.get("dlab") == 0 and ier.get("dlab") == 0 and dll.get("dlab") == 1 and dlm.get("dlab") == 1,
    }

    reset = _verified_transition(transition_model, "reset.line_status_defaults")
    reset_after = reset.get("after", {})
    expected_lsr = (dr_mask if reset_after.get("lsr.data_ready") is True else 0) | (thre_mask if reset_after.get("lsr.thre") is True else 0) | (temt_mask if reset_after.get("lsr.temt") is True else 0)
    if _verified_transition(transition_model, "dlab.select_divisor_latches").get("after", {}).get("lcr.dlab") is not True:
        raise ValueError("verified DLAB transition does not assert DLAB")

    obs_lsr = _observation(probe, "line_status_reset")
    obs_lcr_reset = _observation(probe, "line_control_reset")
    obs_lcr_set = _observation(probe, "line_control_dlab_set")
    obs_dll = _observation(probe, "divisor_lsb_readback")
    obs_dlm = _observation(probe, "divisor_msb_readback")
    obs_lcr_clear = _observation(probe, "line_control_dlab_cleared")
    obs_ier = _observation(probe, "interrupt_enable_after_bank_restore")

    expected_ports = {
        "data": base_port + rb["offset"], "ier": base_port + ier["offset"],
        "lcr": base_port + lcr["offset"], "mcr": base_port + mcr["offset"], "lsr": base_port + lsr["offset"],
    }
    port_checks = {
        "line_status": obs_lsr["port"] == expected_ports["lsr"],
        "line_control_reset": obs_lcr_reset["port"] == expected_ports["lcr"],
        "line_control_set": obs_lcr_set["port"] == expected_ports["lcr"],
        "divisor_lsb": obs_dll["port"] == expected_ports["data"],
        "divisor_msb": obs_dlm["port"] == expected_ports["ier"],
        "line_control_clear": obs_lcr_clear["port"] == expected_ports["lcr"],
        "interrupt_enable": obs_ier["port"] == expected_ports["ier"],
    }

    pattern = probe.get("test_pattern", {})
    behavior_checks = {
        "reset_line_status_exact": obs_lsr["value"] == expected_lsr,
        "reset_dlab_clear": (obs_lcr_reset["value"] & dlab_mask) == 0,
        "dlab_set": (obs_lcr_set["value"] & dlab_mask) == dlab_mask,
        "divisor_lsb_bank_roundtrip": obs_dll["value"] == pattern.get("divisor_lsb"),
        "divisor_msb_bank_roundtrip": obs_dlm["value"] == pattern.get("divisor_msb"),
        "dlab_clear": (obs_lcr_clear["value"] & dlab_mask) == 0,
        "ier_separate_after_bank_restore": obs_ier["value"] == 0,
    }

    if "modem_control_loop_set" in probe.get("observations", {}):
        obs_mcr_before = _observation(probe, "modem_control_before_loop")
        obs_mcr_set = _observation(probe, "modem_control_loop_set")
        obs_loop_lsr = _observation(probe, "line_status_after_loopback_transmit")
        obs_loop_data = _observation(probe, "receiver_buffer_loopback_read")
        obs_drain_lsr = _observation(probe, "line_status_after_loopback_drain")
        obs_mcr_clear = _observation(probe, "modem_control_loop_cleared")
        port_checks.update({
            "modem_control_before_loop": obs_mcr_before["port"] == expected_ports["mcr"],
            "modem_control_loop_set": obs_mcr_set["port"] == expected_ports["mcr"],
            "loopback_line_status": obs_loop_lsr["port"] == expected_ports["lsr"],
            "loopback_receiver_buffer": obs_loop_data["port"] == expected_ports["data"],
            "loopback_drain_status": obs_drain_lsr["port"] == expected_ports["lsr"],
            "modem_control_loop_clear": obs_mcr_clear["port"] == expected_ports["mcr"],
        })
        loop_byte = pattern.get("loopback_data")
        behavior_checks.update({
            "loop_initially_clear": (obs_mcr_before["value"] & loop_mask) == 0,
            "loop_enabled": (obs_mcr_set["value"] & loop_mask) == loop_mask,
            "tx_reaches_rx_data_ready": (obs_loop_lsr["value"] & dr_mask) == dr_mask,
            "tx_rx_loopback_byte_exact": obs_loop_data["value"] == loop_byte,
            "rx_drain_clears_data_ready": (obs_drain_lsr["value"] & dr_mask) == 0,
            "loop_disabled_after_probe": (obs_mcr_clear["value"] & loop_mask) == 0,
        })

    virtual_checks: dict[str, bool] = {}
    if virtual_dlab_execution is not None:
        if virtual_dlab_execution.get("mode") != "in-memory-logical-registers-only":
            raise ValueError("virtual DLAB result is outside the virtual-only boundary")
        if virtual_dlab_execution.get("actuating") is not False or virtual_dlab_execution.get("physical_hardware_proof") is not False:
            raise ValueError("virtual DLAB execution incorrectly claims actuation or physical proof")
        vs = virtual_dlab_execution.get("safety", {})
        if vs.get("hardware_access_performed") is not False or vs.get("physical_writes_performed") is not False:
            raise ValueError("virtual DLAB execution escaped its safety boundary")
        virtual_checks["aurum_virtual_dlab_matches_live_qemu"] = virtual_dlab_execution.get("final_logical_registers", {}).get("selector.line_control") == obs_lcr_set["value"]

    all_checks = {**selector_checks, **port_checks, **behavior_checks, **virtual_checks}
    mismatches = sorted(key for key, matched in all_checks.items() if matched is not True)
    result = {
        "schema": PARITY_SCHEMA,
        "status": "passed" if not mismatches else "failed",
        "physical_hardware_proof": False,
        "live_emulator_proof": True,
        "live_tx_rx_loopback_proof": "modem_control_loop_set" in probe.get("observations", {}) and not any(name in mismatches for name in ("loop_enabled", "tx_reaches_rx_data_ready", "tx_rx_loopback_byte_exact", "rx_drain_clears_data_ready", "loop_disabled_after_probe")),
        "binding_model_identity": binding_model.get("model_identity"),
        "transition_model_identity": transition_model.get("model_identity"),
        "emulator_version": probe.get("emulator_version"),
        "checks": all_checks,
        "mismatches": mismatches,
        "safety": {"physical_hardware_access_performed": False, "physical_writes_performed": False, "firmware_changes_performed": False, "qemu_emulated_io_only": True},
    }
    result["parity_identity"] = _identity(result)
    return result


def build_models_and_virtual_dlab(repo_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    evidence_dir = repo_root / "Projects" / "Codelation" / "driver_evidence"
    binding_payload = json.loads((evidence_dir / "tl16c550d_register_bindings_v0.json").read_text(encoding="utf-8"))
    transition_payload = json.loads((evidence_dir / "tl16c550d_transition_evidence_v0.json").read_text(encoding="utf-8"))
    binding_model = reconcile_evidence([EvidenceClaim(**claim) for claim in binding_payload["claims"]])
    transition_model = reconcile_transition_evidence([TransitionClaim(**claim) for claim in transition_payload["claims"]])
    program_set = synthesize_abstract_driver_programs(transition_model)
    plan = synthesize_lowering_plan(program_set, binding_model)
    dlab_programs = [p for p in program_set["programs"] if any(s.get("transition_key") == "dlab.select_divisor_latches" for s in p.get("steps", []))]
    if len(dlab_programs) != 1:
        raise ValueError("DLAB transition must map to exactly one abstract program")
    virtual = execute_virtual_program(plan, dlab_programs[0]["program_identity"], logical_registers={"selector.line_control": 0})
    return binding_model, transition_model, virtual


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    probe = json.loads(args.probe.read_text(encoding="utf-8"))
    binding_model, transition_model, virtual = build_models_and_virtual_dlab(args.repo_root)
    result = verify_emulator_parity(binding_model, transition_model, probe, virtual_dlab_execution=virtual)
    text = json.dumps(result, sort_keys=True, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
