"""Build a zero-authority register/interrupt shadow model for Pi3 smsc95xx.

This is the next bounded step after the nonbinding functional candidate. It models
only reference-derived register offsets, interrupt masks, endpoint gating, and
write-one-to-clear acknowledgement *intent*. It never opens a device, writes a
register, contacts the Pi, loads a module, changes a binding, or grants authority.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

SCHEMA = "aurum.pi3.smsc95xx.register-interrupt-shadow.v1"
FUNCTIONAL_SCHEMA = "aurum.pi3.smsc95xx.functional-model.v1"
REFERENCE_MANIFEST_SCHEMA = "aurum-pi3-hardware-reference-manifest-v1"

_REQUIRED_FALSE = (
    "mutation_allowed",
    "device_io_allowed",
    "register_write_allowed",
    "interrupt_ack_write_allowed",
    "driver_binding_change_allowed",
    "kernel_module_load_allowed",
    "firmware_mutation_allowed",
    "network_configuration_change_allowed",
    "promotion_allowed",
    "write_authority",
)

_REGISTER_DEFINES = (
    "ID_REV",
    "INT_STS",
    "RX_CFG",
    "TX_CFG",
    "HW_CFG",
    "RX_FIFO_INF",
    "TX_FIFO_INF",
    "PM_CTRL",
    "INT_EP_CTL",
    "MAC_CR",
    "MII_ADDR",
)

_INTERRUPT_SOURCES = (
    ("mac-reset-timeout", "INT_STS_MAC_RTO_", "INT_EP_CTL_MAC_RTO_", "write-one-clear"),
    ("tx-stopped", "INT_STS_TX_STOP_", "INT_EP_CTL_TX_STOP_", "write-one-clear"),
    ("rx-stopped", "INT_STS_RX_STOP_", "INT_EP_CTL_RX_STOP_", "write-one-clear"),
    ("phy-interrupt", "INT_STS_PHY_INT_", "INT_EP_CTL_PHY_INT_", "read-only-source"),
    ("tx-error", "INT_STS_TXE_", "INT_EP_CTL_TXE_", "write-one-clear"),
    ("tx-fifo-underrun", "INT_STS_TDFU_", "INT_EP_CTL_TDFU_", "write-one-clear"),
    ("tx-fifo-overrun", "INT_STS_TDFO_", "INT_EP_CTL_TDFO_", "write-one-clear"),
    ("rx-dropped-frame", "INT_STS_RXDF_", "INT_EP_CTL_RXDF_", "write-one-clear"),
    ("gpio", "INT_STS_GPIOS_", "INT_EP_CTL_GPIOS_", "read-only-source"),
)


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
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


def _source_entry(manifest: Mapping[str, Any], source_id: str) -> Mapping[str, Any]:
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        raise ValueError("reference manifest sources are malformed")
    matches = [item for item in sources if isinstance(item, Mapping) and item.get("id") == source_id]
    if len(matches) != 1:
        raise ValueError(f"reference manifest must contain one {source_id} source")
    return matches[0]


def _define_value(source: str, name: str) -> int:
    pattern = rf"^#define\s+{re.escape(name)}\s+\(?\s*(0[xX][0-9A-Fa-f]+|\d+)\s*\)?(?:\s*/\*.*)?$"
    match = re.search(pattern, source, flags=re.MULTILINE)
    if not match:
        raise ValueError(f"reference header is missing simple integer define {name}")
    return int(match.group(1), 0)


def _require_zero_authority(functional_model: Mapping[str, Any]) -> None:
    authority = functional_model.get("authority")
    if not isinstance(authority, Mapping):
        raise ValueError("functional model authority is malformed")
    for key in (
        "mutation_allowed",
        "driver_binding_change_allowed",
        "kernel_module_load_allowed",
        "firmware_mutation_allowed",
        "network_configuration_change_allowed",
        "promotion_allowed",
        "write_authority",
    ):
        if authority.get(key) is not False:
            raise ValueError(f"functional model must keep {key}=false")


def decode_interrupts(model: Mapping[str, Any], *, int_status: int, int_ep_ctl: int) -> dict[str, Any]:
    """Decode a synthetic status/control pair without performing any register I/O.

    ``w1c_ack_mask`` is only a modeled value describing which observed pulse-status
    bits are defined as write-one-to-clear by the sealed reference semantics. It is
    never written anywhere by this module.
    """
    if int_status < 0 or int_ep_ctl < 0:
        raise ValueError("register values must be non-negative")
    sources = model.get("interrupt_sources")
    if not isinstance(sources, list):
        raise ValueError("interrupt source model is malformed")

    active: list[str] = []
    reportable: list[str] = []
    read_only: list[str] = []
    ack_mask = 0
    known_status_mask = 0
    known_endpoint_mask = 0
    for item in sources:
        if not isinstance(item, Mapping):
            raise ValueError("interrupt source entry is malformed")
        name = str(item["name"])
        status_mask = int(item["status_mask"])
        endpoint_mask = int(item["endpoint_mask"])
        semantics = str(item["clear_semantics"])
        known_status_mask |= status_mask
        known_endpoint_mask |= endpoint_mask
        if int_status & status_mask:
            active.append(name)
            if int_ep_ctl & endpoint_mask:
                reportable.append(name)
            if semantics == "write-one-clear":
                ack_mask |= int_status & status_mask
            elif semantics == "read-only-source":
                read_only.append(name)
            else:
                raise ValueError(f"unknown clear semantics for {name}")

    return {
        "active_sources": active,
        "endpoint_reportable_sources": reportable,
        "read_only_sources": read_only,
        "w1c_ack_mask": ack_mask,
        "unknown_status_bits": int_status & ~known_status_mask & 0xFFFFFFFF,
        "unknown_endpoint_bits": int_ep_ctl & ~known_endpoint_mask & 0xFFFFFFFF,
        "device_io_performed": False,
        "register_write_performed": False,
    }


def build_register_interrupt_model(
    functional_model: Mapping[str, Any],
    reference_manifest: Mapping[str, Any],
    rpi_smsc95xx_h: str,
    upstream_smsc95xx_h: str,
) -> dict[str, Any]:
    if functional_model.get("schema") != FUNCTIONAL_SCHEMA or not _verify_sealed(functional_model):
        raise ValueError("functional model must be a valid sealed receipt")
    if functional_model.get("state") != "verified-offline-functional-model":
        raise ValueError("functional model must be verified before register semantics")
    _require_zero_authority(functional_model)

    if reference_manifest.get("schema") != REFERENCE_MANIFEST_SCHEMA:
        raise ValueError("unexpected Pi3 reference manifest schema")
    rpi_entry = _source_entry(reference_manifest, "raspberry-pi-linux-smsc95xx-h")
    upstream_entry = _source_entry(reference_manifest, "upstream-linux-v6.18-smsc95xx-h")
    if _sha256_text(rpi_smsc95xx_h) != rpi_entry.get("sha256"):
        raise ValueError("Raspberry Pi smsc95xx.h hash does not match pinned reference")
    if _sha256_text(upstream_smsc95xx_h) != upstream_entry.get("sha256"):
        raise ValueError("upstream smsc95xx.h hash does not match pinned reference")

    names = list(_REGISTER_DEFINES)
    for _, status_name, endpoint_name, _ in _INTERRUPT_SOURCES:
        names.extend((status_name, endpoint_name))
    names.extend(("INT_STS_CLEAR_ALL_", "INT_EP_CTL_INTEP_", "INT_EP_CTL_RX_FIFO_"))

    rpi_values = {name: _define_value(rpi_smsc95xx_h, name) for name in names}
    upstream_values = {name: _define_value(upstream_smsc95xx_h, name) for name in names}
    mismatches = {name: [rpi_values[name], upstream_values[name]] for name in names if rpi_values[name] != upstream_values[name]}
    if mismatches:
        raise ValueError(f"Raspberry Pi and upstream register semantics diverge: {mismatches}")

    if rpi_values["INT_STS"] != 0x08 or rpi_values["INT_EP_CTL"] != 0x68:
        raise ValueError("interrupt register offsets differ from the bounded LAN9514 reference")
    if rpi_values["INT_STS_PHY_INT_"] != rpi_values["INT_EP_CTL_PHY_INT_"]:
        raise ValueError("PHY interrupt status/endpoint masks must align")

    interrupt_sources = [
        {
            "name": label,
            "status_define": status_name,
            "status_mask": rpi_values[status_name],
            "endpoint_define": endpoint_name,
            "endpoint_mask": rpi_values[endpoint_name],
            "clear_semantics": clear_semantics,
        }
        for label, status_name, endpoint_name, clear_semantics in _INTERRUPT_SOURCES
    ]

    model: dict[str, Any] = {
        "schema": SCHEMA,
        "state": "verified-offline-register-interrupt-shadow",
        "scope": {
            "mode": "non-actuating-register-interrupt-shadow",
            "controller": "LAN9514/LAN9514i",
            "protected_reference_driver": "smsc95xx",
            "device_io": "forbidden",
        },
        "register_offsets": {name: rpi_values[name] for name in _REGISTER_DEFINES},
        "interrupt_sources": interrupt_sources,
        "endpoint_control": {
            "always_interrupt_packet_mask": rpi_values["INT_EP_CTL_INTEP_"],
            "rx_fifo_has_frame_mask": rpi_values["INT_EP_CTL_RX_FIFO_"],
        },
        "reference_evidence": {
            "functional_model_receipt_sha256": functional_model.get("receipt_sha256"),
            "rpi_smsc95xx_h_sha256": rpi_entry.get("sha256"),
            "upstream_smsc95xx_h_sha256": upstream_entry.get("sha256"),
            "rpi_upstream_constant_agreement": True,
            "microchip_databook_semantics": {
                "INT_STS_offset": "0x008",
                "INT_EP_CTL_offset": "0x068",
                "pulse_status_access": "R/WC",
                "phy_and_gpio_status_access": "RO",
            },
        },
        "authority": {key: False for key in _REQUIRED_FALSE},
        "invariants": {
            "live_pi_contacted": False,
            "device_io_performed": False,
            "register_write_performed": False,
            "interrupt_ack_write_performed": False,
            "driver_binding_changed": False,
            "kernel_changed": False,
            "firmware_changed": False,
            "network_configuration_changed": False,
            "last_known_good_preserved": True,
        },
        "next_gate": "differential-check-candidate-register-interrupt-shadow-semantics",
        "strongest_claim": (
            "The bounded Pi3 smsc95xx candidate now has a deterministic offline register/interrupt shadow model whose interrupt offsets and masks agree between the hash-pinned Raspberry Pi and upstream Linux v6.18 headers, while R/WC acknowledgement intent is kept separate from read-only PHY/GPIO sources. No hardware I/O, register write, binding, module load, mutation, or promotion authority is created."
        ),
    }

    sample = decode_interrupts(
        model,
        int_status=rpi_values["INT_STS_PHY_INT_"] | rpi_values["INT_STS_TXE_"],
        int_ep_ctl=rpi_values["INT_EP_CTL_PHY_INT_"] | rpi_values["INT_EP_CTL_TXE_"],
    )
    if sample["w1c_ack_mask"] != rpi_values["INT_STS_TXE_"] or sample["read_only_sources"] != ["phy-interrupt"]:
        raise ValueError("interrupt clear-semantics self-check failed")

    model["verification"] = {
        "rpi_upstream_defines_compared": len(names),
        "rpi_upstream_define_mismatches": 0,
        "synthetic_mixed_interrupt_self_check": sample,
    }
    model["receipt_sha256"] = _canonical_sha256(model)
    return model
