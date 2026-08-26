"""Generate and differentially verify a zero-authority smsc95xx interrupt candidate.

This is a host-only continuation of the Pi3 LAN9514/smsc95xx shadow-driver lane.
It lowers the sealed register/interrupt model into a portable C decoder that accepts
synthetic INT_STS / INT_EP_CTL values as plain integers. The generated code has no
device handle, MMIO/USB path, register-write primitive, module entry point, binding
hook, firmware path, or promotion authority.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping

from Projects.AdaptiveKernel.pi3_smsc95xx_register_interrupt_model import (
    SCHEMA as REGISTER_MODEL_SCHEMA,
    decode_interrupts,
)

SCHEMA = "aurum.pi3.smsc95xx.register-interrupt-candidate-differential.v1"

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


def _validate_model(model: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if model.get("schema") != REGISTER_MODEL_SCHEMA or not _verify_sealed(model):
        raise ValueError("register/interrupt model must be a valid sealed receipt")
    if model.get("state") != "verified-offline-register-interrupt-shadow":
        raise ValueError("register/interrupt model is not verified")
    authority = model.get("authority")
    if not isinstance(authority, Mapping):
        raise ValueError("register/interrupt model authority is malformed")
    for key in _REQUIRED_FALSE:
        if authority.get(key) is not False:
            raise ValueError(f"register/interrupt model must keep {key}=false")
    sources = model.get("interrupt_sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("register/interrupt source model is missing")
    for item in sources:
        if not isinstance(item, Mapping):
            raise ValueError("interrupt source entry is malformed")
        if item.get("clear_semantics") not in {"write-one-clear", "read-only-source"}:
            raise ValueError("unsupported interrupt clear semantics")
        for key in ("status_mask", "endpoint_mask"):
            value = item.get(key)
            if not isinstance(value, int) or value <= 0 or value > 0xFFFFFFFF:
                raise ValueError(f"interrupt source {key} must be a positive uint32")
    return sources


def synthesize_candidate(model: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    sources = _validate_model(model)
    known_status_mask = 0
    known_endpoint_mask = 0
    w1c_status_mask = 0
    read_only_status_mask = 0
    for item in sources:
        status_mask = int(item["status_mask"])
        endpoint_mask = int(item["endpoint_mask"])
        known_status_mask |= status_mask
        known_endpoint_mask |= endpoint_mask
        if item["clear_semantics"] == "write-one-clear":
            w1c_status_mask |= status_mask
        else:
            read_only_status_mask |= status_mask

    source = f'''/* Aurum generated host-only smsc95xx register/interrupt candidate.
 * ZERO AUTHORITY: synthetic integer decode only; no device I/O or register writes.
 */
#include <stdint.h>

#define AURUM_KNOWN_STATUS_MASK 0x{known_status_mask:08x}u
#define AURUM_KNOWN_ENDPOINT_MASK 0x{known_endpoint_mask:08x}u
#define AURUM_W1C_STATUS_MASK 0x{w1c_status_mask:08x}u
#define AURUM_READ_ONLY_STATUS_MASK 0x{read_only_status_mask:08x}u

typedef struct {{
    uint32_t active_mask;
    uint32_t endpoint_reportable_mask;
    uint32_t read_only_mask;
    uint32_t w1c_ack_mask;
    uint32_t unknown_status_bits;
    uint32_t unknown_endpoint_bits;
}} aurum_smsc95xx_interrupt_decode;

int aurum_smsc95xx_decode_interrupts(uint32_t int_status,
                                     uint32_t int_ep_ctl,
                                     aurum_smsc95xx_interrupt_decode *out) {{
    if (!out) return -1;
    out->active_mask = int_status & AURUM_KNOWN_STATUS_MASK;
    out->endpoint_reportable_mask = int_status & int_ep_ctl & AURUM_KNOWN_STATUS_MASK;
    out->read_only_mask = int_status & AURUM_READ_ONLY_STATUS_MASK;
    out->w1c_ack_mask = int_status & AURUM_W1C_STATUS_MASK;
    out->unknown_status_bits = int_status & ~AURUM_KNOWN_STATUS_MASK;
    out->unknown_endpoint_bits = int_ep_ctl & ~AURUM_KNOWN_ENDPOINT_MASK;
    return 0;
}}
'''
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "state": "synthesized-zero-authority-register-interrupt-candidate",
        "input_register_model_receipt_sha256": model.get("receipt_sha256"),
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "known_status_mask": known_status_mask,
        "known_endpoint_mask": known_endpoint_mask,
        "w1c_status_mask": w1c_status_mask,
        "read_only_status_mask": read_only_status_mask,
        "authority": {key: False for key in _REQUIRED_FALSE},
        "invariants": {
            "live_pi_contacted": False,
            "device_io_performed": False,
            "register_read_performed": False,
            "register_write_performed": False,
            "interrupt_ack_write_performed": False,
            "kernel_module_entrypoint_present": False,
            "driver_binding_path_present": False,
            "last_known_good_preserved": True,
        },
        "next_gate": "host-differential-register-interrupt-scenario-matrix",
    }
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    return source, receipt


class CandidateDecode(ctypes.Structure):
    _fields_ = [
        ("active_mask", ctypes.c_uint32),
        ("endpoint_reportable_mask", ctypes.c_uint32),
        ("read_only_mask", ctypes.c_uint32),
        ("w1c_ack_mask", ctypes.c_uint32),
        ("unknown_status_bits", ctypes.c_uint32),
        ("unknown_endpoint_bits", ctypes.c_uint32),
    ]


def _compile(source: str, root: Path, cc: str | None = None) -> Path:
    compiler = cc or shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if not compiler:
        raise RuntimeError("no C compiler available for candidate differential verification")
    source_path = root / "candidate.c"
    library_path = root / "candidate.so"
    source_path.write_text(source, encoding="utf-8")
    build = subprocess.run(
        [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC", str(source_path), "-o", str(library_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    if build.returncode != 0:
        raise RuntimeError("register/interrupt candidate compilation failed:\n" + build.stdout + build.stderr)
    return library_path


def run_differential(model: Mapping[str, Any], cc: str | None = None) -> dict[str, Any]:
    sources = _validate_model(model)
    source, candidate = synthesize_candidate(model)
    if not _verify_sealed(candidate):
        raise ValueError("candidate receipt is not sealed")

    masks = [int(item["status_mask"]) for item in sources]
    endpoint_masks = [int(item["endpoint_mask"]) for item in sources]
    known_status = int(candidate["known_status_mask"])
    known_endpoint = int(candidate["known_endpoint_mask"])
    unknown_status = (~known_status) & 0xFFFFFFFF
    unknown_endpoint = (~known_endpoint) & 0xFFFFFFFF
    first_unknown_status = unknown_status & -unknown_status if unknown_status else 0
    first_unknown_endpoint = unknown_endpoint & -unknown_endpoint if unknown_endpoint else 0

    scenarios: list[tuple[str, int, int]] = [("none", 0, 0)]
    for index, (status_mask, endpoint_mask) in enumerate(zip(masks, endpoint_masks, strict=True)):
        scenarios.append((f"source-{index}-enabled", status_mask, endpoint_mask))
        scenarios.append((f"source-{index}-masked", status_mask, 0))
    scenarios.extend(
        [
            ("all-known-enabled", known_status, known_endpoint),
            ("mixed-known-half-gated", known_status, known_endpoint & 0xAAAAAAAA),
        ]
    )
    if first_unknown_status:
        scenarios.append(("unknown-status", first_unknown_status, 0))
    if first_unknown_endpoint:
        scenarios.append(("unknown-endpoint", 0, first_unknown_endpoint))
    if first_unknown_status and first_unknown_endpoint:
        scenarios.append(("known-plus-unknown", known_status | first_unknown_status, known_endpoint | first_unknown_endpoint))

    agreements: list[str] = []
    with tempfile.TemporaryDirectory(prefix="aurum-smsc95xx-register-diff-") as temp_dir:
        library = ctypes.CDLL(str(_compile(source, Path(temp_dir), cc)))
        fn = library.aurum_smsc95xx_decode_interrupts
        fn.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(CandidateDecode)]
        fn.restype = ctypes.c_int
        for name, int_status, int_ep_ctl in scenarios:
            expected = decode_interrupts(model, int_status=int_status, int_ep_ctl=int_ep_ctl)
            out = CandidateDecode()
            rc = fn(int_status, int_ep_ctl, ctypes.byref(out))
            if rc != 0:
                raise ValueError(f"candidate rejected synthetic scenario {name}")
            expected_active_mask = 0
            expected_reportable_mask = 0
            expected_read_only_mask = 0
            by_name = {str(item["name"]): item for item in sources}
            for source_name in expected["active_sources"]:
                expected_active_mask |= int(by_name[source_name]["status_mask"])
            for source_name in expected["endpoint_reportable_sources"]:
                expected_reportable_mask |= int(by_name[source_name]["status_mask"])
            for source_name in expected["read_only_sources"]:
                expected_read_only_mask |= int(by_name[source_name]["status_mask"])
            observed = (
                int(out.active_mask),
                int(out.endpoint_reportable_mask),
                int(out.read_only_mask),
                int(out.w1c_ack_mask),
                int(out.unknown_status_bits),
                int(out.unknown_endpoint_bits),
            )
            wanted = (
                expected_active_mask,
                expected_reportable_mask,
                expected_read_only_mask,
                int(expected["w1c_ack_mask"]),
                int(expected["unknown_status_bits"]),
                int(expected["unknown_endpoint_bits"]),
            )
            if observed != wanted:
                raise ValueError(f"candidate/model register-interrupt mismatch for {name}: {observed} != {wanted}")
            agreements.append(name)

    result: dict[str, Any] = {
        "schema": SCHEMA,
        "state": "controlled-register-interrupt-differential-passed",
        "input_register_model_receipt_sha256": model.get("receipt_sha256"),
        "candidate_receipt_sha256": candidate.get("receipt_sha256"),
        "candidate_source_sha256": candidate.get("source_sha256"),
        "scenario_count": len(agreements),
        "agreements": agreements,
        "mismatch_count": 0,
        "verification": {
            "host_compilation": True,
            "shared_library_execution": True,
            "single_source_enabled_and_masked": True,
            "mixed_interrupts": True,
            "unknown_bits": True,
            "w1c_vs_read_only_separation": True,
        },
        "authority": {key: False for key in _REQUIRED_FALSE},
        "invariants": {
            "live_pi_contacted": False,
            "device_io_performed": False,
            "register_read_performed": False,
            "register_write_performed": False,
            "interrupt_ack_write_performed": False,
            "driver_binding_changed": False,
            "kernel_changed": False,
            "last_known_good_preserved": True,
        },
        "next_gate": "model-packet-and-transfer-semantics-before-any-native-binding",
        "strongest_claim": (
            "Aurum generated a portable C interrupt-decoder candidate from the sealed LAN9514/smsc95xx register model and matched the Python reference across per-source gating, mixed interrupts, W1C/read-only separation, and unknown-bit scenarios. The candidate remains host-only and nonbinding; no device I/O, register access, module load, binding, mutation, or promotion authority exists."
        ),
    }
    result["receipt_sha256"] = _canonical_sha256(result)
    return result
