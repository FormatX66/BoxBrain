"""Generate and differentially verify a source-referenced smsc95xx packet candidate.

The generated C accepts synthetic scalar values only. It has no USB handle, packet
buffer, kernel entry point, driver binding path, device I/O primitive, or authority.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import random
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping

from Projects.AdaptiveKernel.pi3_smsc95xx_packet_transfer_model import (
    SCHEMA as PACKET_MODEL_SCHEMA,
    decode_rx_status,
    model_tx_frame,
)

CANDIDATE_SCHEMA = "aurum.pi3.smsc95xx.packet-transfer-candidate.v1"
DIFFERENTIAL_SCHEMA = "aurum.pi3.smsc95xx.packet-transfer-differential.v1"
MANIFEST_SCHEMA = "aurum-pi3-hardware-reference-manifest-v1"
DEFAULT_FUZZ_SEED = 0x9514EC00
DEFAULT_FUZZ_SCENARIOS = 4096

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

_SOURCE_SEMANTIC_TOKENS = (
    "#define SMSC95XX_TX_OVERHEAD (8)",
    "#define SMSC95XX_TX_OVERHEAD_CSUM (12)",
    "skb_pull(skb, 4 + NET_IP_ALIGN);",
    "size = (u16)((header & RX_STS_FL_) >> 16);",
    "align_count = (4 - ((size + NET_IP_ALIGN) % 4)) % 4;",
    "if (skb->len <= 45) return false;",
    "return skb->csum_offset < (len - (4 + 1));",
    "tx_cmd_a = tx_cmd_b | TX_CMD_A_FIRST_SEG_ | TX_CMD_A_LAST_SEG_;",
    "tx_cmd_a += 4;",
    "tx_cmd_b += 4;",
    "tx_cmd_b |= TX_CMD_B_CSUM_ENABLE;",
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


def _normalized_source(value: str) -> str:
    return " ".join(value.split())


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


def _validate_sources(
    manifest: Mapping[str, Any],
    rpi_smsc95xx_c: str,
    upstream_smsc95xx_c: str,
) -> dict[str, Any]:
    inputs = (
        ("raspberry-pi-linux-smsc95xx-c", rpi_smsc95xx_c),
        ("upstream-linux-v6.18-smsc95xx-c", upstream_smsc95xx_c),
    )
    hashes: dict[str, str] = {}
    for source_id, text in inputs:
        entry = _source_entry(manifest, source_id)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest != entry.get("sha256"):
            raise ValueError(f"{source_id} hash does not match pinned reference")
        normalized = _normalized_source(text)
        missing = [token for token in _SOURCE_SEMANTIC_TOKENS if _normalized_source(token) not in normalized]
        if missing:
            raise ValueError(f"{source_id} is missing packet semantics: " + ", ".join(missing))
        hashes[source_id] = digest
    return {
        "hashes": hashes,
        "semantic_tokens_checked_per_source": len(_SOURCE_SEMANTIC_TOKENS),
        "rpi_upstream_semantic_token_mismatches": 0,
    }


def _validate_packet_model(model: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    if model.get("schema") != PACKET_MODEL_SCHEMA or not _verify_sealed(model):
        raise ValueError("packet transfer model must be a valid sealed receipt")
    if model.get("state") != "verified-offline-packet-transfer-shadow":
        raise ValueError("packet transfer model is not verified")
    authority = model.get("authority")
    if not isinstance(authority, Mapping):
        raise ValueError("packet transfer model authority is malformed")
    for key in _REQUIRED_FALSE:
        if authority.get(key) is not False:
            raise ValueError(f"packet transfer model must keep {key}=false")
    invariants = model.get("invariants")
    if not isinstance(invariants, Mapping):
        raise ValueError("packet transfer model invariants are malformed")
    for key in ("live_pi_contacted", "usb_device_opened", "usb_transfer_submitted", "register_write_performed"):
        if invariants.get(key) is not False:
            raise ValueError(f"packet transfer model must keep {key}=false")
    tx = model.get("tx_packet_framing")
    rx = model.get("rx_packet_framing")
    if not isinstance(tx, Mapping) or not isinstance(rx, Mapping):
        raise ValueError("packet transfer framing metadata is malformed")
    expected_tx = {
        "command_word_bytes": 8,
        "checksum_preamble_bytes": 4,
        "first_segment_mask": 0x00002000,
        "last_segment_mask": 0x00001000,
        "buffer_size_mask": 0x000007FF,
        "frame_length_mask": 0x000007FF,
        "checksum_enable_mask": 0x00004000,
        "hardware_checksum_min_frame_length_exclusive": 45,
        "checksum_trailing_guard_bytes": 5,
    }
    expected_rx = {
        "status_word_bytes": 4,
        "data_offset_bytes": 2,
        "frame_length_mask": 0x3FFF0000,
        "frame_length_shift": 16,
        "error_summary_mask": 0x00008000,
        "next_frame_alignment_bytes": 4,
    }
    if any(tx.get(key) != value for key, value in expected_tx.items()):
        raise ValueError("packet transfer TX contract is outside the pinned smsc95xx envelope")
    if any(rx.get(key) != value for key, value in expected_rx.items()):
        raise ValueError("packet transfer RX contract is outside the pinned smsc95xx envelope")
    return tx, rx


def synthesize_packet_candidate(
    packet_model: Mapping[str, Any],
    reference_manifest: Mapping[str, Any],
    rpi_smsc95xx_c: str,
    upstream_smsc95xx_c: str,
) -> tuple[str, dict[str, Any]]:
    tx, rx = _validate_packet_model(packet_model)
    source_verification = _validate_sources(reference_manifest, rpi_smsc95xx_c, upstream_smsc95xx_c)
    source = f'''/* Aurum generated host-only smsc95xx packet-transfer candidate.
 * ZERO AUTHORITY: synthetic scalar transforms only; no USB, packet, or device I/O.
 */
#include <stdint.h>

#define AURUM_TX_FIRST 0x{int(tx["first_segment_mask"]):08x}u
#define AURUM_TX_LAST 0x{int(tx["last_segment_mask"]):08x}u
#define AURUM_TX_LEN_MASK 0x{int(tx["frame_length_mask"]):08x}u
#define AURUM_TX_CSUM 0x{int(tx["checksum_enable_mask"]):08x}u
#define AURUM_RX_LEN_MASK 0x{int(rx["frame_length_mask"]):08x}u
#define AURUM_RX_ERROR 0x{int(rx["error_summary_mask"]):08x}u

typedef struct {{
    uint32_t checksum_requested;
    uint32_t checksum_enabled;
    uint32_t software_checksum_fallback;
    uint32_t checksum_preamble;
    uint32_t tx_cmd_a;
    uint32_t tx_cmd_b;
    uint32_t usb_buffer_length;
    uint32_t framing_overhead_bytes;
}} aurum_smsc95xx_tx_shadow;

typedef struct {{
    uint32_t frame_length;
    uint32_t error_summary;
    uint32_t status_and_align_prefix_bytes;
    uint32_t next_frame_padding_bytes;
    uint32_t payload_length_valid;
}} aurum_smsc95xx_rx_shadow;

int aurum_smsc95xx_model_tx(uint32_t frame_length,
                            uint32_t checksum_requested,
                            uint32_t checksum_start_offset,
                            uint32_t checksum_field_offset,
                            aurum_smsc95xx_tx_shadow *out) {{
    uint32_t payload_after_start;
    uint32_t checksum_enabled = 0u;
    if (!out || frame_length < 1u || frame_length > AURUM_TX_LEN_MASK || checksum_requested > 1u)
        return -1;
    if (checksum_start_offset > 0xffffu || checksum_field_offset > 0xffffu ||
        checksum_start_offset + checksum_field_offset > 0xffffu)
        return -2;
    payload_after_start = frame_length >= checksum_start_offset ? frame_length - checksum_start_offset : 0u;
    if (checksum_requested && frame_length > {int(tx["hardware_checksum_min_frame_length_exclusive"])}u &&
        payload_after_start > {int(tx["checksum_trailing_guard_bytes"])}u &&
        checksum_field_offset < payload_after_start - {int(tx["checksum_trailing_guard_bytes"])}u)
        checksum_enabled = 1u;
    out->checksum_requested = checksum_requested;
    out->checksum_enabled = checksum_enabled;
    out->software_checksum_fallback = checksum_requested && !checksum_enabled;
    out->checksum_preamble = checksum_enabled
        ? ((checksum_start_offset + checksum_field_offset) << 16) | checksum_start_offset
        : 0u;
    out->tx_cmd_a = frame_length | AURUM_TX_FIRST | AURUM_TX_LAST;
    out->tx_cmd_b = frame_length;
    out->framing_overhead_bytes = {int(tx["command_word_bytes"])}u;
    if (checksum_enabled) {{
        out->tx_cmd_a += {int(tx["checksum_preamble_bytes"])}u;
        out->tx_cmd_b += {int(tx["checksum_preamble_bytes"])}u;
        out->tx_cmd_b |= AURUM_TX_CSUM;
        out->framing_overhead_bytes += {int(tx["checksum_preamble_bytes"])}u;
    }}
    out->usb_buffer_length = frame_length + out->framing_overhead_bytes;
    return 0;
}}

int aurum_smsc95xx_decode_rx(uint32_t status_word,
                             uint32_t available_payload_bytes,
                             aurum_smsc95xx_rx_shadow *out) {{
    uint32_t frame_length;
    if (!out) return -1;
    frame_length = (status_word & AURUM_RX_LEN_MASK) >> {int(rx["frame_length_shift"])}u;
    out->frame_length = frame_length;
    out->error_summary = (status_word & AURUM_RX_ERROR) != 0u;
    out->status_and_align_prefix_bytes = {int(rx["status_word_bytes"] + rx["data_offset_bytes"])}u;
    out->next_frame_padding_bytes = ({int(rx["next_frame_alignment_bytes"])}u -
        ((frame_length + {int(rx["data_offset_bytes"])}u) % {int(rx["next_frame_alignment_bytes"])}u)) %
        {int(rx["next_frame_alignment_bytes"])}u;
    out->payload_length_valid = frame_length <= available_payload_bytes;
    return 0;
}}
'''
    receipt: dict[str, Any] = {
        "schema": CANDIDATE_SCHEMA,
        "state": "synthesized-source-referenced-packet-candidate",
        "input_packet_model_receipt_sha256": packet_model.get("receipt_sha256"),
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "reference_sources": source_verification,
        "authority": {key: False for key in _REQUIRED_FALSE},
        "invariants": {
            "live_pi_contacted": False,
            "usb_device_opened": False,
            "usb_transfer_submitted": False,
            "packet_buffer_allocated": False,
            "packet_buffer_mutated": False,
            "kernel_module_entrypoint_present": False,
            "driver_binding_path_present": False,
            "last_known_good_preserved": True,
        },
        "next_gate": "compiled-exhaustive-and-deterministic-fuzz-differential",
    }
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    return source, receipt


class CandidateTx(ctypes.Structure):
    _fields_ = [
        ("checksum_requested", ctypes.c_uint32),
        ("checksum_enabled", ctypes.c_uint32),
        ("software_checksum_fallback", ctypes.c_uint32),
        ("checksum_preamble", ctypes.c_uint32),
        ("tx_cmd_a", ctypes.c_uint32),
        ("tx_cmd_b", ctypes.c_uint32),
        ("usb_buffer_length", ctypes.c_uint32),
        ("framing_overhead_bytes", ctypes.c_uint32),
    ]


class CandidateRx(ctypes.Structure):
    _fields_ = [
        ("frame_length", ctypes.c_uint32),
        ("error_summary", ctypes.c_uint32),
        ("status_and_align_prefix_bytes", ctypes.c_uint32),
        ("next_frame_padding_bytes", ctypes.c_uint32),
        ("payload_length_valid", ctypes.c_uint32),
    ]


def _compile(source: str, root: Path, cc: str | None = None) -> Path:
    compiler = cc or shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if not compiler:
        raise RuntimeError("no C compiler available for packet differential verification")
    source_path = root / "packet-candidate.c"
    library_path = root / "packet-candidate.so"
    source_path.write_text(source, encoding="utf-8")
    build = subprocess.run(
        [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC", str(source_path), "-o", str(library_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    if build.returncode != 0:
        raise RuntimeError("packet candidate compilation failed:\n" + build.stdout + build.stderr)
    return library_path


def run_packet_differential(
    packet_model: Mapping[str, Any],
    reference_manifest: Mapping[str, Any],
    rpi_smsc95xx_c: str,
    upstream_smsc95xx_c: str,
    *,
    cc: str | None = None,
    fuzz_seed: int = DEFAULT_FUZZ_SEED,
    fuzz_scenarios: int = DEFAULT_FUZZ_SCENARIOS,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    if not isinstance(fuzz_scenarios, int) or not 0 <= fuzz_scenarios <= 100_000:
        raise ValueError("fuzz_scenarios must be between 0 and 100000")
    source, candidate = synthesize_packet_candidate(
        packet_model, reference_manifest, rpi_smsc95xx_c, upstream_smsc95xx_c
    )
    scenario_hash = hashlib.sha256()
    counts = {"tx_exhaustive": 0, "tx_boundaries": 0, "rx_exhaustive": 0, "deterministic_fuzz": 0}

    with tempfile.TemporaryDirectory(prefix="aurum-smsc95xx-packet-diff-") as temp_dir:
        library = ctypes.CDLL(str(_compile(source, Path(temp_dir), cc)))
        tx_fn = library.aurum_smsc95xx_model_tx
        tx_fn.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(CandidateTx)]
        tx_fn.restype = ctypes.c_int
        rx_fn = library.aurum_smsc95xx_decode_rx
        rx_fn.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(CandidateRx)]
        rx_fn.restype = ctypes.c_int

        def compare_tx(frame_length: int, start: int | None, field: int | None, bucket: str) -> None:
            expected = model_tx_frame(
                frame_length=frame_length,
                checksum_start_offset=start,
                checksum_field_offset=field,
            )
            out = CandidateTx()
            requested = int(start is not None)
            rc = tx_fn(frame_length, requested, start or 0, field or 0, ctypes.byref(out))
            observed = (
                int(out.checksum_requested), int(out.checksum_enabled), int(out.software_checksum_fallback),
                int(out.checksum_preamble), int(out.tx_cmd_a), int(out.tx_cmd_b),
                int(out.usb_buffer_length), int(out.framing_overhead_bytes),
            )
            wanted = (
                int(expected["checksum_requested"]), int(expected["checksum_enabled"]),
                int(expected["software_checksum_fallback"]), int(expected["checksum_preamble"] or 0),
                int(expected["tx_cmd_a"]), int(expected["tx_cmd_b"]), int(expected["usb_buffer_length"]),
                int(expected["framing_overhead_bytes"]),
            )
            if rc != 0 or observed != wanted:
                raise ValueError(f"packet TX differential mismatch: {(frame_length, start, field, rc, observed, wanted)}")
            counts[bucket] += 1
            scenario_hash.update(json.dumps(["tx", frame_length, start, field, observed], separators=(",", ":")).encode())

        def compare_rx(status_word: int, available: int, bucket: str) -> None:
            expected = decode_rx_status(status_word=status_word, available_payload_bytes=available)
            out = CandidateRx()
            rc = rx_fn(status_word, available, ctypes.byref(out))
            observed = (
                int(out.frame_length), bool(out.error_summary), int(out.status_and_align_prefix_bytes),
                int(out.next_frame_padding_bytes), bool(out.payload_length_valid),
            )
            wanted = (
                int(expected["frame_length"]), bool(expected["error_summary"]),
                int(expected["status_and_align_prefix_bytes"]), int(expected["next_frame_padding_bytes"]),
                bool(expected["payload_length_valid"]),
            )
            if rc != 0 or observed != wanted:
                raise ValueError(f"packet RX differential mismatch: {(status_word, available, rc, observed, wanted)}")
            counts[bucket] += 1
            scenario_hash.update(json.dumps(["rx", status_word, available, observed], separators=(",", ":")).encode())

        for frame_length in range(1, 0x800):
            compare_tx(frame_length, None, None, "tx_exhaustive")
            compare_tx(frame_length, 0, 0, "tx_exhaustive")
        for args in ((45, 20, 2), (46, 0, 0), (64, 34, 16), (128, 100, 22), (128, 100, 23), (1500, 34, 16), (2047, 0, 2041), (2047, 0, 2042)):
            compare_tx(*args, "tx_boundaries")
        for frame_length in range(0x4000):
            compare_rx(frame_length << 16, frame_length, "rx_exhaustive")
            compare_rx((frame_length << 16) | 0x00008000, max(0, frame_length - 1), "rx_exhaustive")

        rng = random.Random(fuzz_seed)
        for index in range(fuzz_scenarios):
            if index % 2 == 0:
                frame_length = rng.randint(1, 0x7FF)
                if rng.getrandbits(1):
                    start = rng.randint(0, min(0xFFFF, frame_length + 32))
                    field = rng.randint(0, min(0xFFFF - start, frame_length + 32))
                    compare_tx(frame_length, start, field, "deterministic_fuzz")
                else:
                    compare_tx(frame_length, None, None, "deterministic_fuzz")
            else:
                compare_rx(rng.getrandbits(32), rng.randint(0, 20_000), "deterministic_fuzz")

    total = sum(counts.values())
    result: dict[str, Any] = {
        "schema": DIFFERENTIAL_SCHEMA,
        "state": "controlled-source-referenced-packet-differential-passed",
        "input_packet_model_receipt_sha256": packet_model.get("receipt_sha256"),
        "candidate_receipt_sha256": candidate.get("receipt_sha256"),
        "candidate_source_sha256": candidate.get("source_sha256"),
        "scenario_counts": counts,
        "scenario_count": total,
        "scenario_matrix_sha256": scenario_hash.hexdigest(),
        "mismatch_count": 0,
        "fuzz_seed": fuzz_seed,
        "verification": {
            "host_compilation": True,
            "shared_library_execution": True,
            "all_tx_frame_lengths": True,
            "tx_checksum_fallback_boundaries": True,
            "all_rx_frame_lengths": True,
            "rx_alignment_and_error_summary": True,
            "deterministic_bounded_fuzz": True,
            "rpi_upstream_source_semantics": True,
        },
        "qpu": {
            "used": False,
            "hardware_submission_performed": False,
            "reason": "The finite packet matrix is exhaustively and deterministically evaluated classically.",
        },
        "authority": {key: False for key in _REQUIRED_FALSE},
        "invariants": {
            "live_pi_contacted": False,
            "usb_device_opened": False,
            "usb_transfer_submitted": False,
            "packet_buffer_allocated": False,
            "packet_buffer_mutated": False,
            "kernel_module_built": False,
            "kernel_module_loaded": False,
            "driver_binding_changed": False,
            "last_known_good_preserved": True,
        },
        "next_gate": "offline-usbnet-lifecycle-and-fault-state-machine-model",
        "strongest_claim": (
            "A source-hash-pinned portable C packet candidate matches the sealed smsc95xx TX/RX shadow across every "
            "representable TX frame length, every RX frame length, checksum fallback boundaries, and a deterministic "
            "bounded fuzz matrix. This remains host-only and is not a USB driver, kernel module, binding proof, hardware "
            "digital twin, or promotion authorization."
        ),
    }
    result["receipt_sha256"] = _canonical_sha256(result)
    return source, candidate, result


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet-model", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--rpi-source", required=True, type=Path)
    parser.add_argument("--upstream-source", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--cc")
    parser.add_argument("--fuzz-seed", type=lambda value: int(value, 0), default=DEFAULT_FUZZ_SEED)
    parser.add_argument("--fuzz-scenarios", type=int, default=DEFAULT_FUZZ_SCENARIOS)
    args = parser.parse_args()
    source, candidate, differential = run_packet_differential(
        _load(args.packet_model),
        _load(args.manifest),
        args.rpi_source.read_text(encoding="utf-8"),
        args.upstream_source.read_text(encoding="utf-8"),
        cc=args.cc,
        fuzz_seed=args.fuzz_seed,
        fuzz_scenarios=args.fuzz_scenarios,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "packet-transfer-candidate.c").write_text(source, encoding="utf-8")
    (args.output_dir / "packet-transfer-candidate.json").write_text(
        json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (args.output_dir / "packet-transfer-differential.json").write_text(
        json.dumps(differential, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "AURUM_PI3_SMSC95XX_PACKET_DIFFERENTIAL "
        f"state={differential['state']} scenarios={differential['scenario_count']} "
        "mismatches=0 live_pi_contacted=false mutation_authority=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
