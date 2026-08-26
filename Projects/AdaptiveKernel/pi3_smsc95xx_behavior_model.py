"""Build and verify a non-actuating functional model for Pi3 LAN9514/smsc95xx.

The model is deliberately narrower than a production driver. It reconstructs the
key controller/driver interactions already supported by independent reference and
physical evidence: exact USB identity, bounded 10/100 link state, RX checksum
feature control, and TX checksum framing overhead. It never opens a device, never
contacts the Pi, and never grants load/binding/mutation/promotion authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "aurum.pi3.smsc95xx.functional-model.v1"
SOURCE_REFINEMENT_SCHEMA = "aurum-pi3-reference-source-refinement-v1"
REFERENCE_MANIFEST_SCHEMA = "aurum-pi3-hardware-reference-manifest-v1"
EXPECTED_DRIVER = "smsc95xx"
EXPECTED_USB_VENDOR = "0424"
EXPECTED_USB_PRODUCT = "ec00"
EXPECTED_PARENT_VENDOR = "0424"
EXPECTED_PARENT_PRODUCT = "9514"
_REQUIRED_FALSE = (
    "mutation_allowed",
    "driver_binding_change_allowed",
    "kernel_module_load_allowed",
    "firmware_mutation_allowed",
    "network_configuration_change_allowed",
    "promotion_allowed",
    "write_authority",
)


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _verify_sealed(value: Mapping[str, Any]) -> bool:
    claimed = value.get("receipt_sha256")
    if not isinstance(claimed, str):
        return False
    body = dict(value)
    body.pop("receipt_sha256", None)
    return claimed == _canonical_sha256(body)


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _source_entry(manifest: Mapping[str, Any], source_id: str) -> Mapping[str, Any]:
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        raise ValueError("reference manifest sources are malformed")
    matches = [item for item in sources if isinstance(item, Mapping) and item.get("id") == source_id]
    if len(matches) != 1:
        raise ValueError(f"reference manifest must contain one {source_id} source")
    return matches[0]


def _define_int(source: str, name: str) -> int:
    pattern = rf"^#define\s+{re.escape(name)}\s+\(?\s*(\d+)\s*\)?\s*$"
    match = re.search(pattern, source, flags=re.MULTILINE)
    if not match:
        raise ValueError(f"reference source is missing integer define {name}")
    return int(match.group(1))


@dataclass(frozen=True)
class BehaviorState:
    identity_verified: bool = False
    reference_attached: bool = False
    carrier: bool = False
    speed_mbps: int | None = None
    duplex: str | None = None
    rx_checksum_enabled: bool = True


def apply_action(state: BehaviorState, action: Mapping[str, Any], model: Mapping[str, Any]) -> tuple[BehaviorState, dict[str, Any]]:
    kind = str(action.get("kind") or "")
    constants = _mapping(model.get("constants"), "model constants")

    if kind == "identify":
        valid = (
            str(action.get("usb_vendor") or "").lower() == EXPECTED_USB_VENDOR
            and str(action.get("usb_product") or "").lower() == EXPECTED_USB_PRODUCT
            and str(action.get("parent_vendor") or "").lower() == EXPECTED_PARENT_VENDOR
            and str(action.get("parent_product") or "").lower() == EXPECTED_PARENT_PRODUCT
        )
        if not valid:
            raise ValueError("controller identity is outside the proven LAN9514/smsc95xx path")
        return replace(state, identity_verified=True), {"accepted": True, "state": "identified"}

    if kind == "attach_reference":
        if not state.identity_verified:
            raise ValueError("reference driver cannot attach before identity is verified")
        if action.get("driver") != EXPECTED_DRIVER:
            raise ValueError("only the protected smsc95xx reference may attach in the model")
        return replace(state, reference_attached=True), {"accepted": True, "state": "attached"}

    if kind == "link":
        if not state.reference_attached:
            raise ValueError("link state requires the protected reference attachment")
        carrier = bool(action.get("carrier"))
        if not carrier:
            return replace(state, carrier=False, speed_mbps=None, duplex=None), {
                "accepted": True,
                "state": "link-down",
            }
        try:
            speed = int(action.get("speed_mbps"))
        except (TypeError, ValueError) as exc:
            raise ValueError("link speed must be numeric") from exc
        duplex = str(action.get("duplex") or "").lower()
        if speed not in {10, 100} or duplex not in {"half", "full"}:
            raise ValueError("link is outside the proven LAN9514 10/100 envelope")
        return replace(state, carrier=True, speed_mbps=speed, duplex=duplex), {
            "accepted": True,
            "state": "link-up",
            "speed_mbps": speed,
            "duplex": duplex,
        }

    if kind == "set_rx_checksum":
        if not state.reference_attached:
            raise ValueError("RX checksum configuration requires reference attachment")
        enabled = action.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError("RX checksum state must be boolean")
        return replace(state, rx_checksum_enabled=enabled), {
            "accepted": True,
            "rx_checksum_enabled": enabled,
        }

    if kind == "tx_prepare":
        if not state.carrier:
            raise ValueError("TX preparation requires link carrier")
        checksum_partial = action.get("checksum_partial")
        if not isinstance(checksum_partial, bool):
            raise ValueError("TX checksum mode must be boolean")
        overhead = int(
            constants[
                "tx_overhead_checksum_bytes" if checksum_partial else "tx_overhead_bytes"
            ]
        )
        payload_len = int(action.get("payload_len") or 0)
        if payload_len < 0:
            raise ValueError("payload length cannot be negative")
        return state, {
            "accepted": True,
            "checksum_partial": checksum_partial,
            "payload_len": payload_len,
            "framed_len": payload_len + overhead,
            "tx_overhead_bytes": overhead,
        }

    if kind in {"write_eeprom", "bind_candidate", "load_module", "replace_kernel", "firmware_write"}:
        raise ValueError("actuating or persistent action is forbidden in the offline model")
    raise ValueError(f"unknown behavior-model action: {kind}")


def replay_trace(model: Mapping[str, Any], actions: list[Mapping[str, Any]]) -> dict[str, Any]:
    state = BehaviorState(
        rx_checksum_enabled=bool(_mapping(model.get("defaults"), "model defaults")["rx_checksum_enabled"])
    )
    outputs: list[dict[str, Any]] = []
    for action in actions:
        state, output = apply_action(state, action, model)
        outputs.append(output)
    return {
        "state": {
            "identity_verified": state.identity_verified,
            "reference_attached": state.reference_attached,
            "carrier": state.carrier,
            "speed_mbps": state.speed_mbps,
            "duplex": state.duplex,
            "rx_checksum_enabled": state.rx_checksum_enabled,
        },
        "outputs": outputs,
    }


def build_functional_model(
    source_refinement: Mapping[str, Any],
    reference_manifest: Mapping[str, Any],
    rpi_smsc95xx_c: str,
    rpi_smsc95xx_h: str,
) -> dict[str, Any]:
    if source_refinement.get("schema") != SOURCE_REFINEMENT_SCHEMA or not _verify_sealed(source_refinement):
        raise ValueError("source-refined reference correlation is not a valid sealed receipt")
    if source_refinement.get("state") != "completed":
        raise ValueError("source-refined correlation must be completed")
    correlation = _mapping(source_refinement.get("correlation"), "source-refined correlation")
    gaps = correlation.get("gaps")
    if not isinstance(gaps, list) or [item.get("id") for item in gaps if isinstance(item, Mapping)] != [
        "candidate-driver-hardware-behavior"
    ]:
        raise ValueError("functional model expects candidate-driver-hardware-behavior as the sole remaining gap")

    if reference_manifest.get("schema") != REFERENCE_MANIFEST_SCHEMA:
        raise ValueError("unexpected Pi3 reference manifest schema")
    target = _mapping(reference_manifest.get("target"), "reference manifest target")
    if target.get("reference_driver") != EXPECTED_DRIVER:
        raise ValueError("reference manifest does not target smsc95xx")

    c_entry = _source_entry(reference_manifest, "raspberry-pi-linux-smsc95xx-c")
    h_entry = _source_entry(reference_manifest, "raspberry-pi-linux-smsc95xx-h")
    if _sha256_text(rpi_smsc95xx_c) != c_entry.get("sha256"):
        raise ValueError("Raspberry Pi smsc95xx.c hash does not match pinned reference")
    if _sha256_text(rpi_smsc95xx_h) != h_entry.get("sha256"):
        raise ValueError("Raspberry Pi smsc95xx.h hash does not match pinned reference")

    required_c_tokens = (
        '#define SMSC_CHIPNAME',
        '"smsc95xx"',
        'DEFAULT_RX_CSUM_ENABLE',
        'DEFAULT_TX_CSUM_ENABLE',
        'smsc95xx_rx_fixup',
        'smsc95xx_tx_fixup',
        'USB_DEVICE(0x0424, 0xec00)',
    )
    missing = [token for token in required_c_tokens if token not in rpi_smsc95xx_c]
    if missing:
        raise ValueError("reference smsc95xx.c is missing required behavior tokens: " + ", ".join(missing))
    for token in ("#define RX_CFG", "#define HW_CFG"):
        if token not in rpi_smsc95xx_h:
            raise ValueError(f"reference smsc95xx.h is missing {token}")

    tx_overhead = _define_int(rpi_smsc95xx_c, "SMSC95XX_TX_OVERHEAD")
    tx_overhead_csum = _define_int(rpi_smsc95xx_c, "SMSC95XX_TX_OVERHEAD_CSUM")
    if tx_overhead != 8 or tx_overhead_csum != 12:
        raise ValueError("reference TX framing overhead is outside the pinned model")

    model: dict[str, Any] = {
        "schema": SCHEMA,
        "state": "verified-offline-functional-model",
        "scope": {
            "controller": "LAN9514/LAN9514i",
            "protected_reference_driver": EXPECTED_DRIVER,
            "usb_parent": "0424:9514",
            "usb_ethernet_function": "0424:ec00",
            "link_speeds_mbps": [10, 100],
            "duplex_modes": ["half", "full"],
            "mode": "non-actuating-shadow-model",
        },
        "defaults": {
            "rx_checksum_enabled": True,
            "tx_checksum_enabled": True,
        },
        "constants": {
            "tx_overhead_bytes": tx_overhead,
            "tx_overhead_checksum_bytes": tx_overhead_csum,
        },
        "supported_actions": [
            "identify",
            "attach_reference",
            "link",
            "set_rx_checksum",
            "tx_prepare",
        ],
        "forbidden_actions": [
            "write_eeprom",
            "bind_candidate",
            "load_module",
            "replace_kernel",
            "firmware_write",
        ],
        "reference_evidence": {
            "source_refinement_receipt_sha256": source_refinement.get("receipt_sha256"),
            "rpi_smsc95xx_c_sha256": c_entry.get("sha256"),
            "rpi_smsc95xx_h_sha256": h_entry.get("sha256"),
            "reference_manifest_source_commit": _mapping(
                reference_manifest.get("source_scope"), "source scope"
            ).get("raspberry_pi_linux_commit"),
            "physical_feature_evidence": "sealed correlation includes reversible rx-checksumming on/off/on canary and healthy final carrier",
        },
        "authority": {key: False for key in _REQUIRED_FALSE},
        "invariants": {
            "live_pi_contacted": False,
            "device_io_performed": False,
            "driver_binding_changed": False,
            "kernel_changed": False,
            "firmware_changed": False,
            "network_configuration_changed": False,
            "last_known_good_preserved": True,
            "mutation_authority_granted": False,
            "promotion_authority_granted": False,
        },
    }

    canonical_trace = [
        {
            "kind": "identify",
            "usb_vendor": EXPECTED_USB_VENDOR,
            "usb_product": EXPECTED_USB_PRODUCT,
            "parent_vendor": EXPECTED_PARENT_VENDOR,
            "parent_product": EXPECTED_PARENT_PRODUCT,
        },
        {"kind": "attach_reference", "driver": EXPECTED_DRIVER},
        {"kind": "link", "carrier": True, "speed_mbps": 100, "duplex": "full"},
        {"kind": "set_rx_checksum", "enabled": False},
        {"kind": "set_rx_checksum", "enabled": True},
        {"kind": "tx_prepare", "payload_len": 1500, "checksum_partial": False},
        {"kind": "tx_prepare", "payload_len": 1500, "checksum_partial": True},
    ]
    replay = replay_trace(model, canonical_trace)
    if replay["state"] != {
        "identity_verified": True,
        "reference_attached": True,
        "carrier": True,
        "speed_mbps": 100,
        "duplex": "full",
        "rx_checksum_enabled": True,
    }:
        raise ValueError("canonical reference trace did not converge to protected physical state")
    if replay["outputs"][-2]["tx_overhead_bytes"] != 8 or replay["outputs"][-1]["tx_overhead_bytes"] != 12:
        raise ValueError("canonical TX framing behavior does not match source constants")

    model["verification"] = {
        "canonical_trace": canonical_trace,
        "canonical_replay": replay,
        "functional_scenarios_passed": 7,
        "physical_state_reproduced": True,
        "reference_tx_framing_reproduced": True,
        "reversible_rx_checksum_sequence_reproduced": True,
    }
    model["next_gate"] = "synthesize-minimal-nonbinding-driver-candidate-from-functional-model"
    model["strongest_claim"] = (
        "Aurum now has a deterministic non-actuating LAN9514/smsc95xx functional model whose controller identity, 10/100 link envelope, reversible RX-checksum behavior, and TX checksum framing agree with sealed physical/reference evidence and hash-pinned Raspberry Pi Linux source. It is not a production driver and grants no mutation or promotion authority."
    )
    model["receipt_sha256"] = _canonical_sha256(model)
    return model


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-refinement", required=True, type=Path)
    parser.add_argument("--reference-manifest", required=True, type=Path)
    parser.add_argument("--smsc95xx-c", required=True, type=Path)
    parser.add_argument("--smsc95xx-h", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    model = build_functional_model(
        _load(args.source_refinement),
        _load(args.reference_manifest),
        args.smsc95xx_c.read_text(encoding="utf-8"),
        args.smsc95xx_h.read_text(encoding="utf-8"),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(model, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "AURUM_PI3_SMSC95XX_FUNCTIONAL_MODEL "
        f"state={model['state']} scenarios={model['verification']['functional_scenarios_passed']} "
        "mutation_authority=false promotion_authority=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
