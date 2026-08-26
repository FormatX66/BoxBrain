"""Prove Raspberry Pi 3 running-kernel package equivalence without mutation.

This module binds a fresh, read-only physical package/kernel fingerprint to the
official Raspberry Pi archive binary package. It never contacts the Pi itself,
never changes a driver/kernel, and never grants mutation or promotion authority.

The strongest successful claim is intentionally narrow: the running kernel bytes
observed on the pinned Pi3 match the kernel bytes shipped in the exact official
Raspberry Pi archive binary package, whose package/source metadata also matches.
That establishes package-to-running-binary provenance, not compiler reproducibility
or permission to replace the protected reference driver.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "aurum.pi3.source-equivalence.v1"
PHYSICAL_SCHEMA = "aurum.pi3.source-equivalence.physical.v1"
FINGERPRINT_SCHEMA = "aurum.pi3.controller-link-fingerprint.v1"
OFFICIAL_ARCHIVE_PREFIX = "https://archive.raspberrypi.com/debian/pool/main/l/linux/"
EXPECTED_MODEL = "Raspberry Pi 3 Model B Rev 1.2"
EXPECTED_SERIAL = "00000000a6a7df7f"
EXPECTED_KERNEL = "6.18.34+rpt-rpi-v8"
EXPECTED_PACKAGE = f"linux-image-{EXPECTED_KERNEL}"
EXPECTED_SOURCE_PACKAGE = "linux"
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


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _verify_sealed(value: Mapping[str, Any]) -> bool:
    claimed = value.get("receipt_sha256")
    if not isinstance(claimed, str):
        return False
    body = dict(value)
    body.pop("receipt_sha256", None)
    return claimed == _canonical_sha256(body)


def _false_authority(value: Mapping[str, Any]) -> bool:
    return all(value.get(key) is False for key in _REQUIRED_FALSE)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_sha256(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _strip_epoch(version: str) -> str:
    return version.split(":", 1)[1] if ":" in version else version


def _parse_source_field(value: str, binary_version: str) -> tuple[str, str]:
    text = value.strip()
    match = re.fullmatch(r"([^\s()]+)\s+\(([^()]+)\)", text)
    if match:
        return match.group(1), match.group(2)
    return text, binary_version


def _deb_field(deb_path: Path, field: str) -> str:
    result = subprocess.run(
        ["dpkg-deb", "-f", str(deb_path), field],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def inspect_official_deb(
    deb_path: Path, *, official_url: str, expected_kernel: str, extract_root: Path
) -> dict[str, Any]:
    if not official_url.startswith(OFFICIAL_ARCHIVE_PREFIX):
        raise ValueError("official package URL is outside the Raspberry Pi archive")
    if not deb_path.is_file():
        raise ValueError("official package file is missing")

    package = _deb_field(deb_path, "Package")
    version = _deb_field(deb_path, "Version")
    architecture = _deb_field(deb_path, "Architecture")
    source_field = _deb_field(deb_path, "Source")
    source_package, source_version = _parse_source_field(source_field, version)

    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True)
    subprocess.run(["dpkg-deb", "-x", str(deb_path), str(extract_root)], check=True)

    expected = extract_root / "boot" / f"vmlinuz-{expected_kernel}"
    if expected.is_file():
        kernel_path = expected
    else:
        matches = sorted(extract_root.rglob(f"vmlinuz-{expected_kernel}"))
        if len(matches) != 1:
            raise ValueError("official package does not contain one exact running-kernel image")
        kernel_path = matches[0]

    return {
        "deb_url": official_url,
        "package": package,
        "version": version,
        "architecture": architecture,
        "source_package": source_package,
        "source_version": source_version,
        "deb_sha256": _sha256_file(deb_path),
        "kernel_binary_path": "/" + kernel_path.relative_to(extract_root).as_posix(),
        "kernel_binary_sha256": _sha256_file(kernel_path),
    }


def validate_source_equivalence(
    physical: Mapping[str, Any],
    fingerprint: Mapping[str, Any],
    official: Mapping[str, Any],
) -> dict[str, Any]:
    if physical.get("schema") != PHYSICAL_SCHEMA:
        raise ValueError("unexpected physical source-equivalence schema")
    if fingerprint.get("schema") != FINGERPRINT_SCHEMA or not _verify_sealed(fingerprint):
        raise ValueError("fingerprint must be a valid sealed receipt")
    if fingerprint.get("state") != "completed-read-only-fingerprint":
        raise ValueError("fingerprint must be complete and non-quarantined")

    physical_authority = physical.get("authority")
    fingerprint_authority = fingerprint.get("authority")
    if not isinstance(physical_authority, Mapping) or not _false_authority(physical_authority):
        raise ValueError("physical evidence must carry explicit zero authority")
    if not isinstance(fingerprint_authority, Mapping) or not _false_authority(fingerprint_authority):
        raise ValueError("fingerprint must carry explicit zero authority")

    target = physical.get("target")
    fp_target = fingerprint.get("target")
    provenance = physical.get("provenance")
    if not isinstance(target, Mapping) or not isinstance(fp_target, Mapping) or not isinstance(provenance, Mapping):
        raise ValueError("physical target/provenance is malformed")

    expected_target = {
        "model": EXPECTED_MODEL,
        "serial": EXPECTED_SERIAL,
        "kernel": EXPECTED_KERNEL,
    }
    for key, expected in expected_target.items():
        if target.get(key) != expected or fp_target.get(key) != expected:
            raise ValueError(f"pinned {key} does not match source-equivalence reference")

    package = str(provenance.get("running_image_package") or "")
    version = str(provenance.get("running_image_package_version") or "")
    architecture = str(provenance.get("running_image_package_architecture") or "")
    source_package = str(provenance.get("running_image_source_package") or "")
    source_version = str(provenance.get("running_image_source_version") or "")
    kernel_path = str(provenance.get("running_kernel_binary_path") or "")
    physical_kernel_sha = str(provenance.get("running_kernel_binary_sha256") or "").lower()

    if package != EXPECTED_PACKAGE:
        raise ValueError("physical running image package does not match pinned kernel")
    if source_package != EXPECTED_SOURCE_PACKAGE:
        raise ValueError("physical running image source package is not linux")
    if not version or not source_version or not architecture:
        raise ValueError("physical package/source metadata is incomplete")
    if not kernel_path or not _valid_sha256(physical_kernel_sha):
        raise ValueError("physical running-kernel hash evidence is incomplete")

    official_url = str(official.get("deb_url") or "")
    official_package = str(official.get("package") or "")
    official_version = str(official.get("version") or "")
    official_arch = str(official.get("architecture") or "")
    official_source_package = str(official.get("source_package") or "")
    official_source_version = str(official.get("source_version") or "")
    official_kernel_path = str(official.get("kernel_binary_path") or "")
    official_deb_sha = str(official.get("deb_sha256") or "").lower()
    official_kernel_sha = str(official.get("kernel_binary_sha256") or "").lower()

    quarantine: list[str] = []
    if not official_url.startswith(OFFICIAL_ARCHIVE_PREFIX):
        quarantine.append("official-package-url-outside-raspberry-pi-archive")
    if official_package != package:
        quarantine.append("official-package-name-mismatch")
    if _strip_epoch(official_version) != _strip_epoch(version):
        quarantine.append("official-package-version-mismatch")
    if official_arch != architecture:
        quarantine.append("official-package-architecture-mismatch")
    if official_source_package != source_package:
        quarantine.append("official-source-package-mismatch")
    if _strip_epoch(official_source_version) != _strip_epoch(source_version):
        quarantine.append("official-source-version-mismatch")
    if not _valid_sha256(official_deb_sha):
        quarantine.append("official-deb-hash-missing")
    if not official_kernel_path.endswith(f"vmlinuz-{EXPECTED_KERNEL}"):
        quarantine.append("official-kernel-path-mismatch")
    if not _valid_sha256(official_kernel_sha):
        quarantine.append("official-kernel-hash-missing")
    if _valid_sha256(official_kernel_sha) and official_kernel_sha != physical_kernel_sha:
        quarantine.append("running-kernel-bytes-differ-from-official-package")

    passed = not quarantine
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "state": (
            "passed-official-package-binary-equivalence"
            if passed
            else "quarantined-source-equivalence"
        ),
        "inputs": {
            "physical_source_commit": physical.get("source_commit"),
            "physical_source_run_id": physical.get("source_run_id"),
            "fingerprint_receipt_sha256": fingerprint.get("receipt_sha256"),
        },
        "target": {
            "model": target.get("model"),
            "serial": target.get("serial"),
            "kernel": target.get("kernel"),
            "architecture": target.get("arch"),
        },
        "physical": {
            "package": package,
            "version": version,
            "architecture": architecture,
            "source_package": source_package,
            "source_version": source_version,
            "kernel_binary_path": kernel_path,
            "kernel_binary_sha256": physical_kernel_sha,
        },
        "official": {
            "deb_url": official_url,
            "package": official_package,
            "version": official_version,
            "architecture": official_arch,
            "source_package": official_source_package,
            "source_version": official_source_version,
            "deb_sha256": official_deb_sha,
            "kernel_binary_path": official_kernel_path,
            "kernel_binary_sha256": official_kernel_sha,
        },
        "checks": {
            "package_name_match": official_package == package,
            "package_version_match": _strip_epoch(official_version) == _strip_epoch(version),
            "package_architecture_match": official_arch == architecture,
            "source_package_match": official_source_package == source_package,
            "source_version_match": _strip_epoch(official_source_version) == _strip_epoch(source_version),
            "running_kernel_bytes_match_official_package": official_kernel_sha == physical_kernel_sha,
            "official_archive_url": official_url.startswith(OFFICIAL_ARCHIVE_PREFIX),
        },
        "quarantine_reasons": quarantine,
        "invariants": {
            "live_pi_contacted_by_official_comparison": False,
            "driver_binding_changed": False,
            "kernel_changed": False,
            "firmware_changed": False,
            "network_configuration_changed": False,
            "mutation_authority_granted": False,
            "promotion_authority_granted": False,
            "last_known_good_preserved": True,
        },
        "authority": {key: False for key in _REQUIRED_FALSE},
        "next_gate": (
            "build-offline-functional-smsc95xx-lan9514-behavior-model"
            if passed
            else "resolve-source-equivalence-quarantine"
        ),
        "strongest_claim": (
            "The exact running-kernel bytes read from the pinned Pi3 match the kernel image shipped in the exact official Raspberry Pi archive binary package, and binary/source package metadata matches. This establishes official package/source-version-to-running-binary equivalence without granting mutation or promotion authority."
            if passed
            else "Official-package-to-running-kernel equivalence failed closed; no mutation or promotion authority exists."
        ),
    }
    receipt["receipt_sha256"] = _canonical_sha256(receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--physical", required=True, type=Path)
    parser.add_argument("--fingerprint", required=True, type=Path)
    parser.add_argument("--official-deb", required=True, type=Path)
    parser.add_argument("--official-url", required=True)
    parser.add_argument("--extract-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    physical = _load(args.physical)
    fingerprint = _load(args.fingerprint)
    target = physical.get("target")
    if not isinstance(target, Mapping):
        raise ValueError("physical target is malformed")
    official = inspect_official_deb(
        args.official_deb,
        official_url=args.official_url,
        expected_kernel=str(target.get("kernel") or ""),
        extract_root=args.extract_root,
    )
    receipt = validate_source_equivalence(physical, fingerprint, official)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "AURUM_PI3_SOURCE_EQUIVALENCE "
        f"state={receipt['state']} "
        "mutation_authority=false promotion_authority=false"
    )
    return 0 if receipt["state"] == "passed-official-package-binary-equivalence" else 2


if __name__ == "__main__":
    raise SystemExit(main())
