"""Bind the pinned Pi3 running source package to protected Raspberry Pi Git source paths.

This gate is deliberately source-only.  It consumes sealed proof that the running
kernel equals the official Raspberry Pi binary package, sealed proof for the pinned
Raspberry Pi/stable USBNet source relation, metadata from an exact official
``linux-source-6.18`` package, and exact extracted source bytes.  It never contacts
or mutates the Pi and it never turns source equivalence into kernel authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "aurum.pi3.source-package-provenance.v1"
STATE = "running-package-protected-source-bound-to-rpi-git"
QUARANTINE_STATE = "source-package-provenance-quarantined"
SOURCE_EQ_SCHEMA = "aurum.pi3.source-equivalence.v1"
SOURCE_EQ_STATE = "passed-official-package-binary-equivalence"
PATCH_SCHEMA = "aurum.pi3.smsc95xx.rpi-usbnet-patch-delta.v1"
PATCH_STATE = "raspberry-pi-usbnet-urb-no-patch-delta"
PACKAGE_META_SCHEMA = "aurum.pi3.official-linux-source-package.v1"
KERNEL = "6.18.34+rpt-rpi-v8"
SOURCE_PACKAGE = "linux"
SOURCE_VERSION = "1:6.18.34-1+rpt1"
SOURCE_BINARY_PACKAGE = "linux-source-6.18"
RPI_COMMIT = "16f1da3c4e94437449d6aa151589ca0ad4b388bb"
PATHS = ("drivers/net/usb/usbnet.c", "drivers/usb/core/urb.c")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
AUTHORITY_FALSE = (
    "mutation_allowed", "device_io_allowed", "usb_transfer_allowed",
    "register_write_allowed", "interrupt_ack_write_allowed",
    "driver_binding_change_allowed", "kernel_module_load_allowed",
    "firmware_mutation_allowed", "network_configuration_change_allowed",
    "promotion_allowed", "write_authority",
)


def canonical_sha256(value: Mapping[str, Any]) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def verify_seal(value: Mapping[str, Any], label: str) -> None:
    claimed = value.get("receipt_sha256")
    if not isinstance(claimed, str):
        raise ValueError(f"{label} is not sealed")
    body = dict(value)
    body.pop("receipt_sha256", None)
    if claimed != canonical_sha256(body):
        raise ValueError(f"{label} seal mismatch")


def require_false(mapping: object, keys: tuple[str, ...], label: str) -> None:
    if not isinstance(mapping, Mapping):
        raise ValueError(f"{label} authority is malformed")
    for key in keys:
        if mapping.get(key) is not False:
            raise ValueError(f"{label} must keep {key}=false")


def normalize_version(value: object) -> str:
    text = str(value or "").strip()
    return text.split(":", 1)[-1]


def validate_source_equivalence(value: Mapping[str, Any]) -> None:
    if value.get("schema") != SOURCE_EQ_SCHEMA or value.get("state") != SOURCE_EQ_STATE:
        raise ValueError("source-equivalence schema/state mismatch")
    verify_seal(value, "source-equivalence receipt")
    require_false(value.get("authority"), tuple(k for k in AUTHORITY_FALSE if k in {
        "mutation_allowed", "driver_binding_change_allowed", "kernel_module_load_allowed",
        "firmware_mutation_allowed", "network_configuration_change_allowed",
        "promotion_allowed", "write_authority"}), "source-equivalence")
    official = value.get("official")
    physical = value.get("physical")
    checks = value.get("checks")
    if not isinstance(official, Mapping) or not isinstance(physical, Mapping):
        raise ValueError("source-equivalence package evidence malformed")
    for item in (official, physical):
        if item.get("source_package") != SOURCE_PACKAGE or item.get("source_version") != SOURCE_VERSION:
            raise ValueError("running source package/version moved")
    if official.get("kernel_binary_sha256") != physical.get("kernel_binary_sha256"):
        raise ValueError("official and running kernel bytes diverge")
    if not isinstance(checks, Mapping) or not checks or any(v is not True for v in checks.values()):
        raise ValueError("source-equivalence checks are not all true")


def validate_patch_delta(value: Mapping[str, Any], source_eq: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    if value.get("schema") != PATCH_SCHEMA or value.get("state") != PATCH_STATE:
        raise ValueError("patch-delta schema/state mismatch")
    verify_seal(value, "patch-delta receipt")
    require_false(value.get("authority"), AUTHORITY_FALSE, "patch-delta")
    if value.get("mismatch_count") != 0:
        raise ValueError("patch-delta contains mismatches")
    if value.get("source_equivalence_receipt_sha256") != source_eq.get("receipt_sha256"):
        raise ValueError("patch-delta is not bound to this running source-equivalence receipt")
    ref = value.get("raspberry_pi_reference")
    if not isinstance(ref, Mapping) or ref.get("commit") != RPI_COMMIT or ref.get("commit_api_object_verified") is not True:
        raise ValueError("patch-delta Raspberry Pi commit is not the pinned verified commit")
    comparisons = value.get("comparisons")
    if not isinstance(comparisons, Mapping) or set(comparisons) != set(PATHS):
        raise ValueError("patch-delta protected source set is incomplete")
    indexed: dict[str, Mapping[str, Any]] = {}
    for path in PATHS:
        item = comparisons[path]
        if not isinstance(item, Mapping) or item.get("byte_identical") is not True:
            raise ValueError(f"{path} is not proven byte-identical in patch-delta evidence")
        expected = item.get("raspberry_pi_sha256")
        if not isinstance(expected, str) or not HEX64.fullmatch(expected):
            raise ValueError(f"{path} Raspberry Pi hash is invalid")
        indexed[path] = item
    return indexed


def validate_package_metadata(value: Mapping[str, Any]) -> None:
    if value.get("schema") != PACKAGE_META_SCHEMA:
        raise ValueError("official source-package metadata schema mismatch")
    if value.get("package") != SOURCE_BINARY_PACKAGE:
        raise ValueError("official source binary package changed")
    if value.get("source_package") != SOURCE_PACKAGE:
        raise ValueError("official source package is not linux")
    if normalize_version(value.get("version")) != normalize_version(SOURCE_VERSION):
        raise ValueError("official source binary package version changed")
    if normalize_version(value.get("source_version")) != normalize_version(SOURCE_VERSION):
        raise ValueError("official source version changed")
    url = value.get("package_url")
    package_hash = value.get("package_sha256")
    archive_hash = value.get("source_archive_sha256")
    if not isinstance(url, str) or not url.startswith("https://archive.raspberrypi.com/debian/pool/main/l/linux/"):
        raise ValueError("source package is not from the official Raspberry Pi archive")
    if not isinstance(package_hash, str) or not HEX64.fullmatch(package_hash):
        raise ValueError("official source package hash is invalid")
    if not isinstance(archive_hash, str) or not HEX64.fullmatch(archive_hash):
        raise ValueError("embedded source archive hash is invalid")


def run_provenance(*, source_equivalence: Mapping[str, Any], patch_delta: Mapping[str, Any],
                   package_metadata: Mapping[str, Any], package_sources: Mapping[str, bytes],
                   rpi_sources: Mapping[str, bytes]) -> dict[str, Any]:
    validate_source_equivalence(source_equivalence)
    expected = validate_patch_delta(patch_delta, source_equivalence)
    validate_package_metadata(package_metadata)
    if set(package_sources) != set(PATHS) or set(rpi_sources) != set(PATHS):
        raise ValueError("exactly the protected USBNet/URB source files are required")

    comparisons: dict[str, Any] = {}
    mismatches: list[str] = []
    for path in PATHS:
        package_hash = sha256(package_sources[path])
        rpi_hash = sha256(rpi_sources[path])
        expected_hash = expected[path]["raspberry_pi_sha256"]
        rpi_matches_pinned = rpi_hash == expected_hash
        package_matches_rpi = package_sources[path] == rpi_sources[path]
        if not rpi_matches_pinned:
            mismatches.append(f"{path}:rpi-source-hash-drift")
        if not package_matches_rpi:
            mismatches.append(f"{path}:source-package-differs-from-rpi-git")
        comparisons[path] = {
            "source_package_sha256": package_hash,
            "raspberry_pi_sha256": rpi_hash,
            "pinned_raspberry_pi_sha256": expected_hash,
            "rpi_source_matches_pinned_receipt": rpi_matches_pinned,
            "source_package_matches_rpi_git": package_matches_rpi,
        }

    passed = not mismatches
    body: dict[str, Any] = {
        "schema": SCHEMA,
        "state": STATE if passed else QUARANTINE_STATE,
        "target": {"kernel": KERNEL, "source_package": SOURCE_PACKAGE, "source_version": SOURCE_VERSION},
        "official_source_package": {
            "package": package_metadata["package"],
            "version": package_metadata["version"],
            "source_package": package_metadata["source_package"],
            "source_version": package_metadata["source_version"],
            "package_url": package_metadata["package_url"],
            "package_sha256": package_metadata["package_sha256"],
            "source_archive_sha256": package_metadata["source_archive_sha256"],
        },
        "raspberry_pi_reference": {"repository": "raspberrypi/linux", "commit": RPI_COMMIT},
        "source_equivalence_receipt_sha256": source_equivalence["receipt_sha256"],
        "patch_delta_receipt_sha256": patch_delta["receipt_sha256"],
        "comparisons": comparisons,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "protected_source_path_binding_proven": passed,
        "full_source_package_git_commit_binding_proven": False,
        "invariants": {
            "live_pi_contacted": False,
            "source_compiled_or_executed": False,
            "usb_device_opened": False,
            "usb_transfer_submitted": False,
            "register_access_performed": False,
            "kernel_code_executed": False,
            "driver_binding_changed": False,
        },
        "authority": {key: False for key in AUTHORITY_FALSE},
        "strongest_claim": (
            "The exact official Raspberry Pi linux-source package corresponding to the running kernel source version contains USBNet and URB source bytes identical to the pinned Raspberry Pi Git commit already verified against signed stable Linux. This binds the protected reference paths used by the candidate model to the running package lineage, but does not prove whole-tree build reproducibility or grant hardware/kernel/mutation/promotion authority."
            if passed else
            "Official source-package provenance for one or more protected USBNet/URB paths did not match the pinned Raspberry Pi Git evidence; the result is quarantined and grants no authority."
        ),
        "next_safe_gate": "whole-tree-build-recipe-provenance-or-bounded-virtual-module-integration" if passed else "repair-source-package-provenance",
    }
    body["receipt_sha256"] = canonical_sha256(body)
    return body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-equivalence", type=Path, required=True)
    parser.add_argument("--patch-delta", type=Path, required=True)
    parser.add_argument("--package-metadata", type=Path, required=True)
    parser.add_argument("--package-usbnet", type=Path, required=True)
    parser.add_argument("--package-urb", type=Path, required=True)
    parser.add_argument("--rpi-usbnet", type=Path, required=True)
    parser.add_argument("--rpi-urb", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    load = lambda p: json.loads(p.read_text(encoding="utf-8-sig"))
    result = run_provenance(
        source_equivalence=load(args.source_equivalence), patch_delta=load(args.patch_delta),
        package_metadata=load(args.package_metadata),
        package_sources={PATHS[0]: args.package_usbnet.read_bytes(), PATHS[1]: args.package_urb.read_bytes()},
        rpi_sources={PATHS[0]: args.rpi_usbnet.read_bytes(), PATHS[1]: args.rpi_urb.read_bytes()},
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"AURUM_PI3_SOURCE_PACKAGE_PROVENANCE state={result['state']} mismatches={result['mismatch_count']} receipt_sha256={result['receipt_sha256']} protected_binding={str(result['protected_source_path_binding_proven']).lower()} write_authority=false")
    return 0 if result["state"] == STATE else 2


if __name__ == "__main__":
    raise SystemExit(main())
