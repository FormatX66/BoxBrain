"""Differentially verify the synthesized Pi3 smsc95xx candidate against its model.

The comparison is intentionally host-only. It compiles the generated portable C
candidate as a shared library, calls it in-process, and compares its bounded state
transitions with the sealed Python functional model. No Pi is contacted and no
kernel/module, device binding, firmware, EEPROM, DMA, or network mutation occurs.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping

from Projects.AdaptiveKernel.pi3_smsc95xx_behavior_model import replay_trace
from Projects.AdaptiveKernel.pi3_smsc95xx_candidate_synth import (
    CANDIDATE_SCHEMA,
    MODEL_SCHEMA,
    synthesize_candidate,
)

SCHEMA = "aurum.pi3.smsc95xx.candidate-differential.v1"


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


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


class CandidateState(ctypes.Structure):
    _fields_ = [
        ("identity_verified", ctypes.c_int),
        ("carrier", ctypes.c_int),
        ("speed_mbps", ctypes.c_uint),
        ("full_duplex", ctypes.c_int),
        ("rx_checksum_enabled", ctypes.c_int),
    ]


def _compile_shared(source: str, root: Path, cc: str | None = None) -> Path:
    compiler = cc or shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if not compiler:
        raise RuntimeError("no C compiler available for differential verification")
    source_path = root / "candidate.c"
    library_path = root / "candidate.so"
    source_path.write_text(source, encoding="utf-8")
    build = subprocess.run(
        [
            compiler,
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-shared",
            "-fPIC",
            str(source_path),
            "-o",
            str(library_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if build.returncode != 0:
        raise RuntimeError("candidate shared-library compilation failed:\n" + build.stdout + build.stderr)
    return library_path


def _bind(library_path: Path) -> ctypes.CDLL:
    lib = ctypes.CDLL(str(library_path))
    lib.aurum_smsc95xx_init.argtypes = [
        ctypes.POINTER(CandidateState),
        ctypes.c_uint16,
        ctypes.c_uint16,
        ctypes.c_uint16,
        ctypes.c_uint16,
    ]
    lib.aurum_smsc95xx_init.restype = ctypes.c_int
    lib.aurum_smsc95xx_set_link.argtypes = [
        ctypes.POINTER(CandidateState),
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.c_int,
    ]
    lib.aurum_smsc95xx_set_link.restype = ctypes.c_int
    lib.aurum_smsc95xx_set_rx_checksum.argtypes = [
        ctypes.POINTER(CandidateState),
        ctypes.c_int,
    ]
    lib.aurum_smsc95xx_set_rx_checksum.restype = ctypes.c_int
    lib.aurum_smsc95xx_tx_frame_len.argtypes = [
        ctypes.POINTER(CandidateState),
        ctypes.c_size_t,
        ctypes.c_int,
    ]
    lib.aurum_smsc95xx_tx_frame_len.restype = ctypes.c_size_t
    return lib


def _model_prefix() -> list[dict[str, Any]]:
    return [
        {
            "kind": "identify",
            "usb_vendor": "0424",
            "usb_product": "ec00",
            "parent_vendor": "0424",
            "parent_product": "9514",
        },
        {"kind": "attach_reference", "driver": "smsc95xx"},
    ]


def run_differential(functional_model: Mapping[str, Any], cc: str | None = None) -> dict[str, Any]:
    if functional_model.get("schema") != MODEL_SCHEMA or not _verify_sealed(functional_model):
        raise ValueError("functional model must be a valid sealed receipt")
    if functional_model.get("state") != "verified-offline-functional-model":
        raise ValueError("functional model is not verified")

    source, candidate_receipt = synthesize_candidate(functional_model)
    if candidate_receipt.get("schema") != CANDIDATE_SCHEMA or not _verify_sealed(candidate_receipt):
        raise ValueError("synthesized candidate receipt is not sealed")

    agreements: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="aurum-smsc95xx-diff-") as temp_dir:
        lib = _bind(_compile_shared(source, Path(temp_dir), cc))

        # Exact identity acceptance and wrong-controller refusal.
        state = CandidateState()
        candidate_rc = lib.aurum_smsc95xx_init(ctypes.byref(state), 0x0424, 0x9514, 0x0424, 0xEC00)
        model_state = replay_trace(functional_model, _model_prefix())["state"]
        if candidate_rc != 0 or state.identity_verified != 1 or model_state["identity_verified"] is not True:
            raise ValueError("candidate/model identity acceptance mismatch")
        agreements.append({"id": "exact-controller-identity", "state": "agrees"})

        bad_state = CandidateState()
        bad_candidate_rc = lib.aurum_smsc95xx_init(ctypes.byref(bad_state), 0x0424, 0x9514, 0x0424, 0x7800)
        model_rejected = False
        try:
            replay_trace(
                functional_model,
                [
                    {
                        "kind": "identify",
                        "usb_vendor": "0424",
                        "usb_product": "7800",
                        "parent_vendor": "0424",
                        "parent_product": "9514",
                    }
                ],
            )
        except ValueError:
            model_rejected = True
        if bad_candidate_rc == 0 or not model_rejected:
            raise ValueError("candidate/model wrong-controller rejection mismatch")
        agreements.append({"id": "wrong-controller-rejection", "state": "agrees"})

        # All proven link modes plus link-down.
        for speed in (10, 100):
            for full_duplex in (0, 1):
                state = CandidateState()
                if lib.aurum_smsc95xx_init(ctypes.byref(state), 0x0424, 0x9514, 0x0424, 0xEC00) != 0:
                    raise ValueError("candidate init failed during link differential")
                candidate_rc = lib.aurum_smsc95xx_set_link(ctypes.byref(state), 1, speed, full_duplex)
                model = replay_trace(
                    functional_model,
                    _model_prefix()
                    + [
                        {
                            "kind": "link",
                            "carrier": True,
                            "speed_mbps": speed,
                            "duplex": "full" if full_duplex else "half",
                        }
                    ],
                )["state"]
                if (
                    candidate_rc != 0
                    or state.carrier != 1
                    or state.speed_mbps != model["speed_mbps"]
                    or state.full_duplex != (1 if model["duplex"] == "full" else 0)
                ):
                    raise ValueError(f"candidate/model link mismatch at {speed} Mbps duplex={full_duplex}")
                agreements.append(
                    {
                        "id": f"link-{speed}-{'full' if full_duplex else 'half'}",
                        "state": "agrees",
                    }
                )

        state = CandidateState()
        lib.aurum_smsc95xx_init(ctypes.byref(state), 0x0424, 0x9514, 0x0424, 0xEC00)
        candidate_rc = lib.aurum_smsc95xx_set_link(ctypes.byref(state), 0, 0, 0)
        model = replay_trace(
            functional_model,
            _model_prefix() + [{"kind": "link", "carrier": False}],
        )["state"]
        if candidate_rc != 0 or state.carrier != 0 or model["carrier"] is not False:
            raise ValueError("candidate/model link-down mismatch")
        agreements.append({"id": "link-down", "state": "agrees"})

        # Reject link speed outside the proven envelope in both implementations.
        state = CandidateState()
        lib.aurum_smsc95xx_init(ctypes.byref(state), 0x0424, 0x9514, 0x0424, 0xEC00)
        candidate_rc = lib.aurum_smsc95xx_set_link(ctypes.byref(state), 1, 1000, 1)
        model_rejected = False
        try:
            replay_trace(
                functional_model,
                _model_prefix()
                + [{"kind": "link", "carrier": True, "speed_mbps": 1000, "duplex": "full"}],
            )
        except ValueError:
            model_rejected = True
        if candidate_rc == 0 or not model_rejected:
            raise ValueError("candidate/model unproven-gigabit rejection mismatch")
        agreements.append({"id": "unproven-gigabit-rejection", "state": "agrees"})

        # RX checksum transitions.
        for enabled in (False, True):
            state = CandidateState()
            lib.aurum_smsc95xx_init(ctypes.byref(state), 0x0424, 0x9514, 0x0424, 0xEC00)
            candidate_rc = lib.aurum_smsc95xx_set_rx_checksum(ctypes.byref(state), int(enabled))
            model = replay_trace(
                functional_model,
                _model_prefix() + [{"kind": "set_rx_checksum", "enabled": enabled}],
            )["state"]
            if candidate_rc != 0 or bool(state.rx_checksum_enabled) is not bool(model["rx_checksum_enabled"]):
                raise ValueError(f"candidate/model RX checksum mismatch enabled={enabled}")
            agreements.append({"id": f"rx-checksum-{'on' if enabled else 'off'}", "state": "agrees"})

        # TX framing at multiple bounded payload sizes and both checksum modes.
        for payload_len in (0, 64, 512, 1500):
            for checksum_partial in (False, True):
                state = CandidateState()
                lib.aurum_smsc95xx_init(ctypes.byref(state), 0x0424, 0x9514, 0x0424, 0xEC00)
                lib.aurum_smsc95xx_set_link(ctypes.byref(state), 1, 100, 1)
                candidate_len = int(
                    lib.aurum_smsc95xx_tx_frame_len(
                        ctypes.byref(state), payload_len, int(checksum_partial)
                    )
                )
                model_result = replay_trace(
                    functional_model,
                    _model_prefix()
                    + [
                        {"kind": "link", "carrier": True, "speed_mbps": 100, "duplex": "full"},
                        {
                            "kind": "tx_prepare",
                            "payload_len": payload_len,
                            "checksum_partial": checksum_partial,
                        },
                    ],
                )
                model_len = int(model_result["outputs"][-1]["framed_len"])
                if candidate_len != model_len:
                    raise ValueError(
                        f"candidate/model TX framing mismatch payload={payload_len} checksum_partial={checksum_partial}"
                    )
                agreements.append(
                    {
                        "id": f"tx-{payload_len}-{'csum' if checksum_partial else 'plain'}",
                        "state": "agrees",
                    }
                )

    result: dict[str, Any] = {
        "schema": SCHEMA,
        "state": "controlled-differential-passed",
        "input_functional_model_receipt_sha256": functional_model.get("receipt_sha256"),
        "candidate_receipt_sha256": candidate_receipt.get("receipt_sha256"),
        "candidate_source_sha256": candidate_receipt.get("source_sha256"),
        "agreement_count": len(agreements),
        "agreements": agreements,
        "mismatch_count": 0,
        "verification": {
            "host_compilation": True,
            "shared_library_execution": True,
            "candidate_vs_model_differential": True,
            "exact_identity_covered": True,
            "wrong_identity_rejection_covered": True,
            "all_proven_link_modes_covered": True,
            "unproven_gigabit_rejection_covered": True,
            "rx_checksum_transitions_covered": True,
            "tx_framing_payload_matrix_covered": True,
        },
        "authority": {
            "mutation_allowed": False,
            "driver_binding_change_allowed": False,
            "kernel_module_load_allowed": False,
            "firmware_mutation_allowed": False,
            "network_configuration_change_allowed": False,
            "promotion_allowed": False,
            "write_authority": False,
        },
        "invariants": {
            "live_pi_contacted": False,
            "device_io_performed": False,
            "physical_driver_changed": False,
            "kernel_changed": False,
            "last_known_good_preserved": True,
            "mutation_authority_granted": False,
            "promotion_authority_granted": False,
        },
        "milestone": "first-controlled-nonbinding-candidate-verification-complete",
        "next_gate": "expand-native-candidate-scope-with-register-interrupt-behavior-before-any-binding",
        "strongest_claim": (
            "The Aurum-generated nonbinding C candidate agrees with the sealed LAN9514/smsc95xx functional model across exact identity, "
            "wrong-identity rejection, every proven 10/100 half/full link mode, link-down, unproven-gigabit rejection, RX checksum transitions, "
            "and a bounded TX framing matrix. This is controlled host-process evidence only and does not prove a kernel driver, physical binding, "
            "interrupt/register behavior, or promotion safety."
        ),
    }
    result["receipt_sha256"] = _canonical_sha256(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cc")
    args = parser.parse_args()
    result = run_differential(_load(args.model), args.cc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"AURUM_PI3_SMSC95XX_DIFFERENTIAL_OK scenarios={result['agreement_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
