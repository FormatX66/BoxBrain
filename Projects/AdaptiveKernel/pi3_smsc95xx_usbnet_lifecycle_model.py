"""Build a sealed, zero-authority smsc95xx/usbnet lifecycle and fault shadow."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import deque
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping

PACKET_DIFFERENTIAL_SCHEMA = "aurum.pi3.smsc95xx.packet-transfer-differential.v1"
QPU_SCHEMA = "aurum-pi3-qpu-routing-reference-v1"
MANIFEST_SCHEMA = "aurum-pi3-hardware-reference-manifest-v1"
SCHEMA = "aurum.pi3.smsc95xx.usbnet-lifecycle-shadow.v1"

_REQUIRED_FALSE = (
    "mutation_allowed",
    "device_io_allowed",
    "usb_transfer_allowed",
    "register_write_allowed",
    "interrupt_ack_write_allowed",
    "driver_binding_change_allowed",
    "kernel_module_load_allowed",
    "firmware_mutation_allowed",
    "network_configuration_change_allowed",
    "promotion_allowed",
    "write_authority",
)

_SMSC_TOKENS = (
    "smsc95xx_bind",
    "smsc95xx_reset",
    "smsc95xx_rx_fixup",
    "smsc95xx_tx_fixup",
    "smsc95xx_suspend",
    "smsc95xx_resume",
    "smsc95xx_autosuspend",
)
_USBNET_TOKENS = (
    "usbnet_probe",
    "usbnet_disconnect",
    "usbnet_open",
    "usbnet_stop",
    "usbnet_suspend",
    "usbnet_resume",
    "EVENT_RX_HALT",
    "EVENT_TX_HALT",
    "EVENT_LINK_RESET",
    "usbnet_defer_kevent",
)

ACTIONS = (
    "probe_success",
    "open_success",
    "stop",
    "link_up",
    "link_down",
    "rx_halt",
    "recover_rx",
    "tx_halt",
    "recover_tx",
    "link_reset",
    "suspend",
    "resume_success",
    "disconnect",
)


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    ).hexdigest()


def _verify_sealed(value: Mapping[str, Any]) -> bool:
    claimed = value.get("receipt_sha256")
    if not isinstance(claimed, str):
        return False
    body = dict(value)
    body.pop("receipt_sha256", None)
    return claimed == _canonical_sha256(body)


def _source_entry(manifest: Mapping[str, Any], source_id: str) -> Mapping[str, Any]:
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError("reference manifest schema is not supported")
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        raise ValueError("reference manifest sources are malformed")
    for item in sources:
        if isinstance(item, Mapping) and item.get("id") == source_id:
            return item
    raise ValueError(f"reference manifest is missing {source_id}")


def _validate_source(
    manifest: Mapping[str, Any], source_id: str, text: str, required_tokens: tuple[str, ...]
) -> str:
    entry = _source_entry(manifest, source_id)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if digest != entry.get("sha256"):
        raise ValueError(f"{source_id} hash does not match pinned reference")
    missing = [token for token in required_tokens if token not in text]
    if missing:
        raise ValueError(f"{source_id} is missing lifecycle semantics: " + ", ".join(missing))
    return digest


def _validate_inputs(
    packet_differential: Mapping[str, Any],
    qpu_router: Mapping[str, Any],
    reference_manifest: Mapping[str, Any],
    sources: Mapping[str, str],
) -> dict[str, Any]:
    if packet_differential.get("schema") != PACKET_DIFFERENTIAL_SCHEMA or not _verify_sealed(packet_differential):
        raise ValueError("packet differential must be a valid sealed receipt")
    if packet_differential.get("state") != "controlled-source-referenced-packet-differential-passed":
        raise ValueError("packet differential gate has not passed")
    if packet_differential.get("mismatch_count") != 0:
        raise ValueError("packet differential contains mismatches")
    authority = packet_differential.get("authority")
    if not isinstance(authority, Mapping):
        raise ValueError("packet differential authority is malformed")
    for key in _REQUIRED_FALSE:
        if authority.get(key) is not False:
            raise ValueError(f"packet differential must keep {key}=false")
    invariants = packet_differential.get("invariants")
    if not isinstance(invariants, Mapping):
        raise ValueError("packet differential invariants are malformed")
    for key in ("live_pi_contacted", "usb_device_opened", "usb_transfer_submitted", "driver_binding_changed"):
        if invariants.get(key) is not False:
            raise ValueError(f"packet differential must keep {key}=false")

    if qpu_router.get("schema") != QPU_SCHEMA or not _verify_sealed(qpu_router):
        raise ValueError("QPU router must be a valid sealed receipt")
    qpu_model = qpu_router.get("model")
    if not isinstance(qpu_model, Mapping):
        raise ValueError("QPU router model is malformed")
    if qpu_model.get("hardware_digital_twin") is not False:
        raise ValueError("QPU router must not be treated as a hardware twin")
    if qpu_model.get("hardware_submission_performed") is not False or qpu_model.get("submission") is not None:
        raise ValueError("QPU router records an unexpected hardware submission")

    specs = (
        ("raspberry-pi-linux-smsc95xx-c", _SMSC_TOKENS),
        ("upstream-linux-v6.18-smsc95xx-c", _SMSC_TOKENS),
        ("raspberry-pi-linux-usbnet-c", _USBNET_TOKENS),
        ("upstream-linux-v6.18-usbnet-c", _USBNET_TOKENS),
    )
    hashes = {
        source_id: _validate_source(reference_manifest, source_id, sources[source_id], tokens)
        for source_id, tokens in specs
    }
    return {
        "source_hashes": hashes,
        "smsc95xx_tokens_checked_per_source": len(_SMSC_TOKENS),
        "usbnet_tokens_checked_per_source": len(_USBNET_TOKENS),
        "rpi_upstream_semantic_token_mismatches": 0,
    }


@dataclass(frozen=True, order=True)
class LifecycleState:
    present: bool = False
    bound: bool = False
    opened: bool = False
    suspended: bool = False
    carrier: bool = False
    rx_halted: bool = False
    tx_halted: bool = False
    disconnected: bool = False


def _valid_state(state: LifecycleState) -> bool:
    if state.bound and not state.present:
        return False
    if state.opened and not state.bound:
        return False
    if state.carrier and (not state.opened or state.suspended):
        return False
    if (state.rx_halted or state.tx_halted) and (not state.opened or state.suspended):
        return False
    if state.disconnected and any(
        (state.present, state.bound, state.opened, state.suspended, state.carrier, state.rx_halted, state.tx_halted)
    ):
        return False
    return True


def transition(state: LifecycleState, action: str) -> tuple[LifecycleState, bool, str]:
    if action not in ACTIONS:
        raise ValueError(f"unknown lifecycle action: {action}")
    result = state
    accepted = False
    reason = "precondition-refused"
    if action == "probe_success" and not state.present:
        result = LifecycleState(present=True, bound=True)
        accepted, reason = True, "device-probed-and-shadow-bound"
    elif action == "open_success" and state.present and state.bound and not state.opened and not state.suspended:
        result = replace(state, opened=True)
        accepted, reason = True, "usbnet-open-shadow"
    elif action == "stop" and state.opened and not state.suspended:
        result = replace(state, opened=False, carrier=False, rx_halted=False, tx_halted=False)
        accepted, reason = True, "usbnet-stop-shadow"
    elif action == "link_up" and state.opened and not state.suspended:
        result = replace(state, carrier=True)
        accepted, reason = True, "carrier-on-shadow"
    elif action == "link_down" and state.opened and not state.suspended:
        result = replace(state, carrier=False)
        accepted, reason = True, "carrier-off-shadow"
    elif action == "rx_halt" and state.opened and not state.suspended:
        result = replace(state, rx_halted=True)
        accepted, reason = True, "rx-halt-deferred-event-shadow"
    elif action == "recover_rx" and state.rx_halted and not state.suspended:
        result = replace(state, rx_halted=False)
        accepted, reason = True, "rx-halt-clear-shadow"
    elif action == "tx_halt" and state.opened and not state.suspended:
        result = replace(state, tx_halted=True)
        accepted, reason = True, "tx-halt-deferred-event-shadow"
    elif action == "recover_tx" and state.tx_halted and not state.suspended:
        result = replace(state, tx_halted=False)
        accepted, reason = True, "tx-halt-clear-shadow"
    elif action == "link_reset" and state.opened and not state.suspended:
        result = replace(state, rx_halted=False, tx_halted=False)
        accepted, reason = True, "link-reset-work-item-shadow"
    elif action == "suspend" and state.present and state.bound and not state.suspended:
        result = replace(state, suspended=True, carrier=False, rx_halted=False, tx_halted=False)
        accepted, reason = True, "usbnet-suspend-shadow"
    elif action == "resume_success" and state.suspended:
        result = replace(state, suspended=False, carrier=False, rx_halted=False, tx_halted=False)
        accepted, reason = True, "usbnet-resume-shadow"
    elif action == "disconnect" and state.present:
        result = LifecycleState(disconnected=True)
        accepted, reason = True, "usbnet-disconnect-shadow"
    if not _valid_state(result):
        raise ValueError(f"lifecycle action produced an invalid state: {action}")
    return result, accepted, reason


def _state_key(state: LifecycleState) -> str:
    return "".join("1" if value else "0" for value in asdict(state).values())


def explore_state_graph() -> dict[str, Any]:
    initial = LifecycleState()
    queue: deque[LifecycleState] = deque([initial])
    states = {initial}
    transitions: list[dict[str, Any]] = []
    accepted_count = 0
    refused_count = 0
    while queue:
        state = queue.popleft()
        for action in ACTIONS:
            next_state, accepted, reason = transition(state, action)
            transitions.append(
                {
                    "from": _state_key(state),
                    "action": action,
                    "to": _state_key(next_state),
                    "accepted": accepted,
                    "reason": reason,
                }
            )
            if accepted:
                accepted_count += 1
            else:
                refused_count += 1
            if next_state not in states:
                states.add(next_state)
                queue.append(next_state)
    transitions.sort(key=lambda item: (item["from"], item["action"], item["to"]))
    state_rows = [{"id": _state_key(state), **asdict(state)} for state in sorted(states, key=_state_key)]
    matrix_hash = hashlib.sha256(
        json.dumps(transitions, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if not all(_valid_state(state) for state in states):
        raise ValueError("lifecycle graph contains an invalid state")
    return {
        "initial_state": _state_key(initial),
        "state_count": len(states),
        "transition_count": len(transitions),
        "accepted_transition_count": accepted_count,
        "refused_transition_count": refused_count,
        "transition_matrix_sha256": matrix_hash,
        "states": state_rows,
        "invariants": {
            "carrier_requires_open_awake_bound_device": True,
            "halt_requires_open_awake_bound_device": True,
            "disconnect_clears_operational_state": True,
            "suspend_clears_carrier_and_halts": True,
            "recovery_clears_only_modeled_halt": True,
            "invalid_transitions_are_refused_without_state_change": True,
        },
    }


def _replay(actions: tuple[str, ...]) -> dict[str, Any]:
    state = LifecycleState()
    steps = []
    for action in actions:
        next_state, accepted, reason = transition(state, action)
        steps.append({"action": action, "accepted": accepted, "reason": reason, "state": asdict(next_state)})
        state = next_state
    return {"actions": list(actions), "steps": steps, "final_state": asdict(state)}


def build_lifecycle_model(
    *,
    packet_differential: Mapping[str, Any],
    qpu_router: Mapping[str, Any],
    reference_manifest: Mapping[str, Any],
    sources: Mapping[str, str],
) -> dict[str, Any]:
    source_verification = _validate_inputs(packet_differential, qpu_router, reference_manifest, sources)
    graph = explore_state_graph()
    paths = {
        "healthy_lifecycle": _replay(("probe_success", "open_success", "link_up", "stop", "disconnect")),
        "rx_fault_recovery": _replay(("probe_success", "open_success", "link_up", "rx_halt", "recover_rx")),
        "tx_fault_link_reset": _replay(("probe_success", "open_success", "link_up", "tx_halt", "link_reset")),
        "suspend_resume_disconnect": _replay(("probe_success", "open_success", "link_up", "suspend", "resume_success", "disconnect")),
        "reprobe_after_disconnect": _replay(("probe_success", "disconnect", "probe_success", "open_success")),
    }
    if not all(step["accepted"] for path in paths.values() for step in path["steps"]):
        raise ValueError("canonical lifecycle path contains a refused transition")
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "state": "verified-offline-usbnet-lifecycle-fault-model",
        "inputs": {
            "packet_differential_receipt_sha256": packet_differential.get("receipt_sha256"),
            "qpu_router_receipt_sha256": qpu_router.get("receipt_sha256"),
        },
        "source_verification": source_verification,
        "graph": graph,
        "canonical_paths": paths,
        "qpu": {
            "preserved_router_available": True,
            "router_candidate_kind": qpu_router["model"].get("candidate_kind"),
            "router_is_hardware_digital_twin": False,
            "used": False,
            "hardware_submission_performed": False,
            "reason": "The finite lifecycle graph is exactly reachable by classical breadth-first exploration; the preserved router concerns experiment-path selection, not controller lifecycle emulation.",
        },
        "authority": {key: False for key in _REQUIRED_FALSE},
        "invariants": {
            "live_pi_contacted": False,
            "usb_device_opened": False,
            "usb_transfer_submitted": False,
            "driver_probe_performed": False,
            "driver_binding_changed": False,
            "kernel_module_built": False,
            "kernel_module_loaded": False,
            "kernel_changed": False,
            "firmware_changed": False,
            "network_configuration_changed": False,
            "last_known_good_preserved": True,
        },
        "next_gate": "host-compiled-usbnet-lifecycle-candidate-differential",
        "strongest_claim": (
            "Hash-pinned Raspberry Pi and upstream smsc95xx/usbnet sources support a finite offline lifecycle and fault "
            "shadow whose complete reachable graph preserves probe/open/stop, link, halt recovery, suspend/resume, "
            "disconnect, and re-probe invariants. It performs no USB or driver operation and is not a kernel driver, "
            "binding proof, hardware digital twin, or promotion authorization."
        ),
    }
    result["receipt_sha256"] = _canonical_sha256(result)
    return result


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet-differential", required=True, type=Path)
    parser.add_argument("--qpu-router", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--rpi-smsc95xx", required=True, type=Path)
    parser.add_argument("--upstream-smsc95xx", required=True, type=Path)
    parser.add_argument("--rpi-usbnet", required=True, type=Path)
    parser.add_argument("--upstream-usbnet", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = build_lifecycle_model(
        packet_differential=_load(args.packet_differential),
        qpu_router=_load(args.qpu_router),
        reference_manifest=_load(args.manifest),
        sources={
            "raspberry-pi-linux-smsc95xx-c": args.rpi_smsc95xx.read_text(encoding="utf-8"),
            "upstream-linux-v6.18-smsc95xx-c": args.upstream_smsc95xx.read_text(encoding="utf-8"),
            "raspberry-pi-linux-usbnet-c": args.rpi_usbnet.read_text(encoding="utf-8"),
            "upstream-linux-v6.18-usbnet-c": args.upstream_usbnet.read_text(encoding="utf-8"),
        },
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "AURUM_PI3_SMSC95XX_USBNET_LIFECYCLE "
        f"state={result['state']} states={result['graph']['state_count']} "
        f"transitions={result['graph']['transition_count']} live_pi_contacted=false mutation_authority=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
