"""Validate a read-only Raspberry Pi 3 Ethernet/controller fingerprint.

This module consumes evidence collected from the pinned experimental Pi3 and turns it
into a fail-closed receipt.  It never contacts hardware and never grants mutation,
driver-binding, promotion, or recovery authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA = "aurum.pi3.controller-link-fingerprint.v1"
RAW_SCHEMA = "aurum.pi3.controller-link-fingerprint.raw.v1"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _hex4(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 4 and all(c in "0123456789abcdef" for c in text)


def _false(value: Any) -> bool:
    return value is False


def validate_fingerprint(raw: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
    if raw.get("schema") != RAW_SCHEMA:
        raise ValueError("unexpected raw fingerprint schema")
    if identity.get("schema") != "aurum-pi3-pinned-identity-v1":
        raise ValueError("unexpected pinned identity schema")
    if identity.get("production_nodes_allowed") is not False:
        raise ValueError("pinned Pi3 identity must exclude production nodes")

    target = raw.get("target") if isinstance(raw.get("target"), dict) else {}
    ethernet = raw.get("ethernet") if isinstance(raw.get("ethernet"), dict) else {}
    provenance = raw.get("provenance") if isinstance(raw.get("provenance"), dict) else {}
    authority = raw.get("authority") if isinstance(raw.get("authority"), dict) else {}

    required_false = (
        "mutation_allowed",
        "driver_binding_change_allowed",
        "kernel_module_load_allowed",
        "firmware_mutation_allowed",
        "network_configuration_change_allowed",
        "promotion_allowed",
        "write_authority",
    )
    if any(not _false(authority.get(key)) for key in required_false):
        raise ValueError("read-only fingerprint must carry explicit zero authority")

    model = str(target.get("model") or "")
    serial = str(target.get("serial") or "").strip().lower()
    kernel = str(target.get("kernel") or "").strip()
    identity_match = (
        str(identity.get("model_marker") or "") in model
        and serial == str(identity.get("serial") or "").strip().lower()
    )

    interface = str(ethernet.get("interface") or "").strip()
    driver = str(ethernet.get("driver") or "").strip()
    carrier = str(ethernet.get("carrier") or "").strip()
    speed_raw = ethernet.get("speed_mbps")
    try:
        speed_mbps = int(speed_raw) if speed_raw not in (None, "") else None
    except (TypeError, ValueError):
        speed_mbps = None
    duplex = str(ethernet.get("duplex") or "").strip().lower()
    usb_vendor = str(ethernet.get("usb_vendor_id") or "").strip().lower()
    usb_product = str(ethernet.get("usb_product_id") or "").strip().lower()

    packages = provenance.get("kernel_packages")
    if not isinstance(packages, list):
        packages = []
    packages = [str(x).strip() for x in packages if str(x).strip()]
    package_owner = str(provenance.get("modules_package_owner") or "").strip()
    headers_owner = str(provenance.get("headers_package_owner") or "").strip()
    proc_version = str(provenance.get("proc_version") or "").strip()

    checks = {
        "pinned_identity_match": identity_match,
        "protected_driver_match": driver == "smsc95xx",
        "interface_observed": bool(interface),
        "carrier_observed": carrier in {"0", "1"},
        "usb_function_identity_observed": _hex4(usb_vendor) and _hex4(usb_product),
        "link_speed_observed": speed_mbps is not None and speed_mbps > 0,
        "link_speed_within_fast_ethernet": speed_mbps is not None and 0 < speed_mbps <= 100,
        "duplex_observed": duplex in {"full", "half"},
        "kernel_observed": bool(kernel),
        "proc_version_observed": bool(proc_version),
        "kernel_package_candidates_observed": bool(packages),
        "modules_package_owner_observed": bool(package_owner),
        "headers_package_owner_observed": bool(headers_owner),
    }

    quarantine_reasons: list[str] = []
    if not checks["pinned_identity_match"]:
        quarantine_reasons.append("pinned-pi3-identity-mismatch")
    if driver and not checks["protected_driver_match"]:
        quarantine_reasons.append("protected-driver-mismatch")
    if speed_mbps is not None and speed_mbps > 100:
        quarantine_reasons.append("observed-speed-outside-smsc95xx-fast-ethernet-envelope")

    gaps: list[str] = []
    for check, gap in (
        ("usb_function_identity_observed", "usb-controller-function-identity"),
        ("link_speed_observed", "negotiated-link-speed"),
        ("duplex_observed", "negotiated-duplex"),
        ("kernel_package_candidates_observed", "kernel-package-candidates"),
        ("modules_package_owner_observed", "running-modules-package-owner"),
        ("headers_package_owner_observed", "running-headers-package-owner"),
    ):
        if not checks[check]:
            gaps.append(gap)

    if quarantine_reasons:
        state = "quarantined"
    elif gaps:
        state = "completed-with-read-only-gaps"
    else:
        state = "completed-read-only-fingerprint"

    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "state": state,
        "observed_at_utc": raw.get("observed_at_utc"),
        "source_commit": raw.get("source_commit"),
        "source_run_id": raw.get("source_run_id"),
        "target": target,
        "ethernet": ethernet,
        "provenance": {
            "proc_version": proc_version,
            "kernel_packages": packages,
            "modules_package_owner": package_owner,
            "headers_package_owner": headers_owner,
        },
        "checks": checks,
        "gaps": gaps,
        "quarantine_reasons": quarantine_reasons,
        "authority": {key: False for key in required_false},
        "next_gate": (
            "resolve-identity-or-driver-quarantine-before-any-driver-experiment"
            if quarantine_reasons
            else "correlate-observed-controller-link-and-package-provenance-with-pinned-references"
        ),
        "strongest_claim": (
            "Read-only physical evidence from the pinned experimental Pi3 was validated against its exact model/serial and protected smsc95xx path. The receipt records observed USB-function identity, negotiated link state, and running-kernel package provenance where available; it grants no mutation or promotion authority."
            if not quarantine_reasons
            else "The read-only physical fingerprint failed a pinned identity/driver safety check and is quarantined; no mutation or promotion authority exists."
        ),
    }
    canonical = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
    receipt["receipt_sha256"] = hashlib.sha256(canonical).hexdigest()
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument(
        "--identity",
        type=Path,
        default=Path("Projects/AdaptiveDrivers/config/pi3-identity.json"),
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    receipt = validate_fingerprint(_load(args.input), _load(args.identity))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "AURUM_PI3_CONTROLLER_FINGERPRINT "
        f"state={receipt['state']} gaps={len(receipt['gaps'])} "
        "mutation_allowed=false promotion_allowed=false"
    )
    return 0 if receipt["state"] != "quarantined" else 2


if __name__ == "__main__":
    raise SystemExit(main())
