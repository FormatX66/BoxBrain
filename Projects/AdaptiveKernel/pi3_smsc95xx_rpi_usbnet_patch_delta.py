"""Offline Raspberry Pi versus signed-stable USBNet/URB source delta.

This bounded, source-only gate consumes sealed upstream receipts and exact
pinned source bytes.  It never imports, compiles, or executes the sources and
has no authority to contact a device or change a running system.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "aurum.pi3.smsc95xx.rpi-usbnet-patch-delta.v1"
STATE = "raspberry-pi-usbnet-urb-no-patch-delta"
MISMATCH_STATE = "raspberry-pi-usbnet-urb-patch-delta-mismatch"
MANIFEST_SCHEMA = "aurum.pi3.smsc95xx.rpi-usbnet-patch-delta-manifest.v1"
COMMIT_VERIFICATION_SCHEMA = "aurum.raspberry-pi-linux-commit-verification.v1"
REFERENCE_SCHEMA = "aurum.pi3.smsc95xx.linux-usbnet-urb-reference-differential.v1"
REFERENCE_STATE = "linux-usbnet-urb-reference-compatible"
SOURCE_EQ_SCHEMA = "aurum.pi3.source-equivalence.v1"
SOURCE_EQ_STATE = "passed-official-package-binary-equivalence"
PI_KERNEL = "6.18.34+rpt-rpi-v8"
PI_SOURCE_VERSION = "1:6.18.34-1+rpt1"
RPI_REF = "rpi-6.18.y"
RPI_COMMIT = "16f1da3c4e94437449d6aa151589ca0ad4b388bb"
STABLE_TAG = "v6.18.34"
STABLE_TAG_OBJECT = "71659eca49870e2f9d33412084034abe9c3e453f"
STABLE_COMMIT = "18ad16ce4a6b2714583fd1e1044c6ea8e53b3519"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_AUTHORITY_FALSE = (
    "mutation_allowed", "device_io_allowed", "usb_transfer_allowed",
    "register_write_allowed", "interrupt_ack_write_allowed",
    "driver_binding_change_allowed", "kernel_module_load_allowed",
    "firmware_mutation_allowed", "network_configuration_change_allowed",
    "promotion_allowed", "write_authority",
)
_PATHS = ("drivers/net/usb/usbnet.c", "drivers/usb/core/urb.c")


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _verify_seal(value: Mapping[str, Any]) -> bool:
    claimed = value.get("receipt_sha256")
    if not isinstance(claimed, str):
        return False
    body = dict(value)
    body.pop("receipt_sha256", None)
    return claimed == _canonical_sha256(body)


def _require_false(mapping: object, keys: tuple[str, ...], label: str) -> None:
    if not isinstance(mapping, Mapping):
        raise ValueError(f"{label} is malformed")
    for key in keys:
        if mapping.get(key) is not False:
            raise ValueError(f"{label} must keep {key}=false")


def _validate_source_equivalence(receipt: Mapping[str, Any], target: Mapping[str, Any]) -> None:
    if receipt.get("schema") != SOURCE_EQ_SCHEMA or receipt.get("state") != SOURCE_EQ_STATE:
        raise ValueError("source-equivalence receipt has the wrong schema/state")
    if not _verify_seal(receipt):
        raise ValueError("source-equivalence receipt is not sealed")
    actual_target = receipt.get("target")
    official = receipt.get("official")
    physical = receipt.get("physical")
    checks = receipt.get("checks")
    if not isinstance(actual_target, Mapping) or actual_target.get("kernel") != target.get("kernel"):
        raise ValueError("source-equivalence receipt targets a different kernel")
    if not isinstance(official, Mapping) or not isinstance(physical, Mapping):
        raise ValueError("source-equivalence package evidence is malformed")
    for evidence in (official, physical):
        if evidence.get("source_package") != target.get("source_package"):
            raise ValueError("source package changed from the patch-delta manifest")
        if evidence.get("source_version") != target.get("source_version"):
            raise ValueError("source version changed from the patch-delta manifest")
    if official.get("kernel_binary_sha256") != physical.get("kernel_binary_sha256"):
        raise ValueError("official and physical kernel hashes diverge")
    if not isinstance(checks, Mapping) or not checks or not all(v is True for v in checks.values()):
        raise ValueError("source-equivalence checks are not all true")
    _require_false(
        receipt.get("authority"),
        tuple(key for key in _REQUIRED_AUTHORITY_FALSE if key not in {
            "device_io_allowed", "usb_transfer_allowed", "register_write_allowed",
            "interrupt_ack_write_allowed",
        }),
        "source-equivalence authority",
    )


def _validate_reference(
    receipt: Mapping[str, Any], source_equivalence: Mapping[str, Any], manifest: Mapping[str, Any]
) -> None:
    if receipt.get("schema") != REFERENCE_SCHEMA or receipt.get("state") != REFERENCE_STATE:
        raise ValueError("Linux USBNet/URB reference receipt has the wrong schema/state")
    if not _verify_seal(receipt) or receipt.get("mismatch_count") != 0:
        raise ValueError("Linux USBNet/URB reference receipt is unsealed or mismatched")
    _require_false(receipt.get("authority"), _REQUIRED_AUTHORITY_FALSE, "reference authority")
    invariants = receipt.get("invariants")
    if not isinstance(invariants, Mapping) or not invariants or any(v is not False for v in invariants.values()):
        raise ValueError("reference receipt zero-authority invariants failed")
    reference = receipt.get("reference")
    running = receipt.get("pi_running_source")
    stable = manifest["signed_stable"]
    files = {entry["path"]: entry for entry in manifest["files"]}
    if not isinstance(reference, Mapping) or not isinstance(running, Mapping):
        raise ValueError("reference receipt source evidence is malformed")
    if reference.get("commit") != stable.get("commit"):
        raise ValueError("reference stable commit differs from the manifest")
    if reference.get("tag_object_sha") != stable.get("tag_object_sha"):
        raise ValueError("reference signed tag object differs from the manifest")
    if reference.get("usbnet_sha256") != files[_PATHS[0]]["signed_stable_sha256"]:
        raise ValueError("reference usbnet hash differs from the manifest")
    if reference.get("urb_sha256") != files[_PATHS[1]]["signed_stable_sha256"]:
        raise ValueError("reference URB hash differs from the manifest")
    if running.get("official_binary_equivalence_receipt_sha256") != source_equivalence.get("receipt_sha256"):
        raise ValueError("reference receipt is not bound to this source-equivalence receipt")


def _validate_manifest(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError("patch-delta manifest schema is invalid")
    target = manifest.get("target")
    rpi = manifest.get("raspberry_pi")
    stable = manifest.get("signed_stable")
    files = manifest.get("files")
    if not all(isinstance(item, Mapping) for item in (target, rpi, stable)):
        raise ValueError("patch-delta manifest references are malformed")
    if target != {"kernel": PI_KERNEL, "source_package": "linux", "source_version": PI_SOURCE_VERSION}:
        raise ValueError("patch-delta manifest target moved from the pinned running source")
    if rpi.get("repository") != "raspberrypi/linux" or stable.get("repository") != "gregkh/linux":
        raise ValueError("patch-delta manifest repositories are invalid")
    if rpi.get("ref") != RPI_REF or rpi.get("commit") != RPI_COMMIT:
        raise ValueError("Raspberry Pi source reference moved from the pinned commit")
    if stable.get("tag") != STABLE_TAG or stable.get("tag_object_sha") != STABLE_TAG_OBJECT:
        raise ValueError("signed stable tag moved from the pinned reference")
    if stable.get("commit") != STABLE_COMMIT:
        raise ValueError("signed stable source moved from the pinned commit")
    if not isinstance(files, list) or len(files) != len(_PATHS):
        raise ValueError("patch-delta manifest must contain exactly two source files")
    indexed: dict[str, Mapping[str, Any]] = {}
    for entry in files:
        if not isinstance(entry, Mapping) or entry.get("path") in indexed:
            raise ValueError("patch-delta manifest file entry is malformed or duplicated")
        path = entry.get("path")
        if path not in _PATHS or entry.get("expected_relation") not in {"identical", "different"}:
            raise ValueError("patch-delta manifest file path/relation is invalid")
        for key in ("raspberry_pi_sha256", "signed_stable_sha256"):
            if not isinstance(entry.get(key), str) or not _HEX64.fullmatch(entry[key]):
                raise ValueError(f"patch-delta manifest {key} is invalid")
        indexed[path] = entry
    if set(indexed) != set(_PATHS):
        raise ValueError("patch-delta manifest source set is incomplete")
    return indexed


def _validate_commit_verification(value: Mapping[str, Any], rpi: Mapping[str, Any]) -> None:
    if value.get("schema") != COMMIT_VERIFICATION_SCHEMA:
        raise ValueError("Raspberry Pi commit verification schema is invalid")
    for key in ("repository", "commit", "message", "parents"):
        if value.get(key) != rpi.get(key if key != "message" else "expected_commit_message"):
            raise ValueError(f"Raspberry Pi commit verification {key} changed")
    if value.get("api_object_present") is not True:
        raise ValueError("Raspberry Pi commit was not confirmed by the GitHub API")


def _delta(left: bytes, right: bytes, preview_limit: int = 40) -> dict[str, Any]:
    identical = left == right
    try:
        left_lines = left.decode("utf-8").splitlines()
        right_lines = right.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("reference source is not UTF-8 text") from exc
    diff = list(difflib.unified_diff(left_lines, right_lines, fromfile="raspberry-pi", tofile="signed-stable", lineterm=""))
    added = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
    deleted = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))
    diff_bytes = ("\n".join(diff) + ("\n" if diff else "")).encode("utf-8")
    return {
        "byte_identical": identical,
        "raspberry_pi_bytes": len(left),
        "signed_stable_bytes": len(right),
        "raspberry_pi_lines": len(left_lines),
        "signed_stable_lines": len(right_lines),
        "added_lines": added,
        "deleted_lines": deleted,
        "unified_diff_sha256": _sha256(diff_bytes),
        "diff_preview": diff[:preview_limit],
        "diff_preview_truncated": len(diff) > preview_limit,
    }


def run_patch_delta(
    *, reference_receipt: Mapping[str, Any], source_equivalence: Mapping[str, Any],
    manifest: Mapping[str, Any], rpi_commit_verification: Mapping[str, Any],
    rpi_sources: Mapping[str, bytes], stable_sources: Mapping[str, bytes],
) -> dict[str, Any]:
    files = _validate_manifest(manifest)
    _validate_source_equivalence(source_equivalence, manifest["target"])
    _validate_reference(reference_receipt, source_equivalence, manifest)
    _validate_commit_verification(rpi_commit_verification, manifest["raspberry_pi"])
    if set(rpi_sources) != set(_PATHS) or set(stable_sources) != set(_PATHS):
        raise ValueError("exactly the two manifest source files are required")

    comparisons: dict[str, Any] = {}
    mismatches: list[str] = []
    for path in _PATHS:
        entry = files[path]
        rpi_hash = _sha256(rpi_sources[path])
        stable_hash = _sha256(stable_sources[path])
        if rpi_hash != entry["raspberry_pi_sha256"] or stable_hash != entry["signed_stable_sha256"]:
            raise ValueError(f"{path} content hash does not match the pinned manifest")
        delta = _delta(rpi_sources[path], stable_sources[path])
        actual_relation = "identical" if delta["byte_identical"] else "different"
        relation_matches = actual_relation == entry["expected_relation"]
        if not relation_matches:
            mismatches.append(f"{path}:expected-{entry['expected_relation']}-got-{actual_relation}")
        comparisons[path] = {
            "expected_relation": entry["expected_relation"],
            "actual_relation": actual_relation,
            "relation_matches": relation_matches,
            "raspberry_pi_sha256": rpi_hash,
            "signed_stable_sha256": stable_hash,
            **delta,
        }

    passed = not mismatches and all(item["byte_identical"] for item in comparisons.values())
    body: dict[str, Any] = {
        "schema": SCHEMA,
        "state": STATE if passed else MISMATCH_STATE,
        "target": dict(manifest["target"]),
        "raspberry_pi_reference": {
            "repository": manifest["raspberry_pi"]["repository"],
            "ref": manifest["raspberry_pi"]["ref"],
            "commit": manifest["raspberry_pi"]["commit"],
            "commit_api_object_verified": True,
            "commit_verification_sha256": _canonical_sha256(rpi_commit_verification),
        },
        "signed_stable_reference": dict(manifest["signed_stable"]),
        "manifest_sha256": _canonical_sha256(manifest),
        "upstream_reference_receipt_sha256": reference_receipt["receipt_sha256"],
        "source_equivalence_receipt_sha256": source_equivalence["receipt_sha256"],
        "comparisons": comparisons,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "running_source_package_to_rpi_git_commit_binding_proven": False,
        "invariants": {
            "live_pi_contacted": False,
            "source_executed_or_compiled": False,
            "usb_device_opened": False,
            "usb_transfer_submitted": False,
            "register_access_performed": False,
            "kernel_code_executed": False,
            "driver_binding_changed": False,
        },
        "authority": {key: False for key in _REQUIRED_AUTHORITY_FALSE},
        "strongest_claim": (
            "At the exact pinned commits, Raspberry Pi linux and signed stable Linux v6.18.34 contain "
            "byte-identical drivers/net/usb/usbnet.c and drivers/usb/core/urb.c files. This is offline "
            "source evidence only; it does not bind the running Raspberry Pi source package to the pinned "
            "Raspberry Pi Git commit and grants no hardware, kernel, mutation, or promotion authority."
            if passed else
            "The pinned Raspberry Pi and signed-stable USBNet/URB source relation did not match its manifest; "
            "the evidence is quarantined and grants no hardware, kernel, mutation, or promotion authority."
        ),
        "next_safe_gate": "source-package-patch-series-provenance-for-running-kernel",
    }
    body["receipt_sha256"] = _canonical_sha256(body)
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-receipt", type=Path, required=True)
    parser.add_argument("--source-equivalence", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--rpi-commit-verification", type=Path, required=True)
    parser.add_argument("--rpi-usbnet-source", type=Path, required=True)
    parser.add_argument("--rpi-urb-source", type=Path, required=True)
    parser.add_argument("--stable-usbnet-source", type=Path, required=True)
    parser.add_argument("--stable-urb-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    load = lambda path: json.loads(path.read_text(encoding="utf-8-sig"))
    receipt = run_patch_delta(
        reference_receipt=load(args.reference_receipt),
        source_equivalence=load(args.source_equivalence),
        manifest=load(args.manifest),
        rpi_commit_verification=load(args.rpi_commit_verification),
        rpi_sources={_PATHS[0]: args.rpi_usbnet_source.read_bytes(), _PATHS[1]: args.rpi_urb_source.read_bytes()},
        stable_sources={_PATHS[0]: args.stable_usbnet_source.read_bytes(), _PATHS[1]: args.stable_urb_source.read_bytes()},
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["state"] == STATE else 1


if __name__ == "__main__":
    raise SystemExit(main())
