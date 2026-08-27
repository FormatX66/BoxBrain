"""Fail-closed static contract for the Pi3 kernel-shaped smsc95xx shadow."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[3]
MANIFEST = ROOT / "candidate.json"
SOURCE = ROOT / "aurum_pi3_smsc95xx_kernel_shadow.c"
KBUILD = ROOT / "Kbuild"
PASS_STATE = "verified-inert-kernel-shadow-compile-only"
PROVENANCE_STATE = "running-package-protected-source-bound-to-rpi-git"

FORBIDDEN_SOURCE_PATTERNS = {
    "autoload alias": r"\bMODULE_ALIAS\s*\(",
    "autoload device table": r"\bMODULE_DEVICE_TABLE\s*\(",
    "module parameter": r"\bmodule_param(?:_named)?\s*\(",
    "module exit": r"\bmodule_exit\s*\(",
    "module self-request": r"\brequest_module\s*\(",
    "dynamic symbol lookup": r"\b(?:symbol_get|__symbol_get|kallsyms_lookup_name)\s*\(",
    "userspace execution": r"\bcall_usermodehelper\s*\(",
    "USB driver declaration": r"\bstruct\s+usb_driver\b",
    "USB device table declaration": r"\bstruct\s+usb_device_id\b",
    "network operations declaration": r"\bstruct\s+net_device_ops\b",
    "USB driver registration": r"\b(?:module_usb_driver|usb_register|usb_register_driver)\s*\(",
    "network registration": r"\b(?:register_netdev|register_netdevice)\s*\(",
    "driver binding": r"\b(?:device_bind_driver|driver_attach|device_driver_attach)\s*\(",
    "sysfs registration": r"\b(?:sysfs_create_file|device_create_file|class_create)\s*\(",
    "firmware request": r"\brequest_firmware(?:_direct|_into_buf|_nowait)?\s*\(",
    "USB URB submission": r"\busb_submit_urb\s*\(",
    "USB control/bulk I/O": r"\b(?:usb_control_msg|usb_bulk_msg)\s*\(",
    "USB clear halt": r"\busb_clear_halt\s*\(",
    "memory-mapped hardware write": r"\b(?:writeb|writew|writel|writeq|iowrite8|iowrite16|iowrite32|iowrite64)\s*\(",
    "network carrier mutation": r"\bnetif_carrier_(?:on|off)\s*\(",
    "network feature mutation": r"\b(?:netdev_update_features|dev_change_flags|dev_set_mtu)\s*\(",
    "boot or power transition": r"\b(?:kernel_restart|orderly_reboot|emergency_restart|machine_restart|kernel_power_off|orderly_poweroff)\s*\(",
}

REQUIRED_FALSE = (
    "load_allowed", "successful_load_possible", "registers_device_driver",
    "registers_network_device", "registers_sysfs_interface", "performs_hardware_io",
    "submits_usb_transfers", "writes_registers", "changes_driver_binding",
    "changes_firmware", "changes_boot_configuration", "changes_network_configuration",
    "self_loads_or_requests_modules", "production_nodes_allowed", "promotion_allowed",
    "write_authority",
)


class ContractError(ValueError):
    pass


def canonical_sha256(value: Mapping[str, Any]) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value: bool, message: str) -> None:
    if not value:
        raise ContractError(message)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    require(isinstance(value, dict), f"{path.name} must contain one JSON object")
    return value


def verify_sealed_receipt(value: Mapping[str, Any], expected_sha: str) -> None:
    claimed = value.get("receipt_sha256")
    require(isinstance(claimed, str), "source-package provenance receipt is not sealed")
    require(claimed == expected_sha, "source-package provenance receipt identity moved")
    body = dict(value)
    body.pop("receipt_sha256", None)
    require(canonical_sha256(body) == claimed, "source-package provenance receipt seal mismatch")


def validate_candidate(root: Path = ROOT, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    manifest_path = root / "candidate.json"
    source_path = root / "aurum_pi3_smsc95xx_kernel_shadow.c"
    kbuild_path = root / "Kbuild"
    for path in (manifest_path, source_path, kbuild_path):
        require(path.is_file(), f"required kernel-shadow file missing: {path.name}")

    manifest = load_json(manifest_path)
    require(manifest.get("schema") == "aurum.adaptive-kernel.kernel-shadow-candidate.v1", "unexpected candidate schema")
    require(manifest.get("candidate_id") == "pi3-smsc95xx-kernel-shadow-compile-v1", "candidate identity moved")
    target = manifest.get("target") or {}
    require(target.get("model_marker") == "Raspberry Pi 3 Model B Rev 1.2", "target model moved")
    require(target.get("architecture") == "aarch64", "candidate must remain ARM64-only")
    require(target.get("exact_kernel_release") == "6.18.34+rpt-rpi-v8", "exact kernel release moved")
    require(target.get("reference_driver") == "smsc95xx", "reference driver moved")
    require(target.get("reference_driver_replaced") is False, "reference driver must not be replaced")

    basis = manifest.get("basis") or {}
    provenance_path = repo_root / str(basis.get("source_package_receipt") or "")
    semantic_path = repo_root / str(basis.get("semantic_source") or "")
    require(provenance_path.is_file(), "sealed source-package provenance basis is missing")
    require(semantic_path.is_file(), "sealed semantic source basis is missing")
    provenance = load_json(provenance_path)
    expected_receipt = str(basis.get("source_package_receipt_sha256") or "")
    verify_sealed_receipt(provenance, expected_receipt)
    require(provenance.get("state") == PROVENANCE_STATE, "source-package provenance did not pass")
    require(provenance.get("protected_source_path_binding_proven") is True, "protected source binding is not proven")
    require(provenance.get("full_source_package_git_commit_binding_proven") is False, "basis unexpectedly claims whole-tree provenance")
    require(provenance.get("mismatch_count") == 0, "source-package provenance contains mismatches")
    authority = provenance.get("authority")
    require(isinstance(authority, Mapping) and authority and all(value is False for value in authority.values()),
            "source-package provenance must remain zero-authority")

    expected_blob = str(basis.get("semantic_source_git_blob_sha1") or "")
    actual_blob = git_blob_sha1(semantic_path.read_bytes())
    require(actual_blob == expected_blob, "semantic shadow basis moved")

    build = manifest.get("build") or {}
    require(build.get("mode") == "compile-only", "build mode must remain compile-only")
    require(build.get("kbuild_target") == "modules", "only Kbuild modules target is allowed")
    require(build.get("artifact_retained") is False, "compiled artifact must not be retained")
    require(build.get("exact_vermagic_required") is True, "exact vermagic must be required")
    for key in ("module_aliases_allowed", "device_table_symbols_allowed", "forbidden_unresolved_capability_symbols_allowed"):
        require(build.get(key) is False, f"build.{key} must remain false")

    safety = manifest.get("safety") or {}
    for key in REQUIRED_FALSE:
        require(safety.get(key) is False, f"safety.{key} must remain false")
    require(safety.get("init_behavior") == "return-negative-eperm", "module init must remain hard -EPERM")
    require(safety.get("autoload_aliases") == [], "autoload aliases must remain empty")

    source = source_path.read_text(encoding="utf-8")
    for label, pattern in FORBIDDEN_SOURCE_PATTERNS.items():
        require(re.search(pattern, source) is None, f"forbidden kernel-shadow capability: {label}")
    init = re.compile(
        r"static\s+int\s+__init\s+aurum_pi3_smsc95xx_kernel_shadow_init\s*\(\s*void\s*\)"
        r"\s*\{\s*return\s+-EPERM\s*;\s*\}", re.MULTILINE)
    require(init.search(source) is not None, "kernel-shadow init must contain only return -EPERM")
    require(source.count("module_init(aurum_pi3_smsc95xx_kernel_shadow_init);") == 1,
            "exactly one inert module init declaration is required")
    require('MODULE_INFO(aurum_mode, "kernel-shadow-compile-only");' in source,
            "kernel-shadow compile-only metadata is missing")
    for token in (
        "AURUM_PARENT_VID 0x0424u", "AURUM_PARENT_PID 0x9514u",
        "AURUM_USB_VID 0x0424u", "AURUM_USB_PID 0xec00u",
        "AURUM_TX_OVERHEAD 8u", "AURUM_TX_OVERHEAD_CSUM 12u",
        "aurum_smsc95xx_init", "aurum_smsc95xx_set_link",
        "aurum_smsc95xx_set_rx_checksum", "aurum_smsc95xx_tx_frame_len",
        "speed_mbps != 10u && speed_mbps != 100u",
        "struct sk_buff", "struct urb", "netdev_features_t",
        "struct usb_device_descriptor", "struct usb_ctrlrequest",
    ):
        require(token in source, f"kernel-shadow semantic/type surface missing: {token}")

    kbuild_lines = [line.strip() for line in kbuild_path.read_text(encoding="utf-8").splitlines()
                    if line.strip() and not line.lstrip().startswith("#")]
    require(kbuild_lines == ["obj-m := aurum_pi3_smsc95xx_kernel_shadow.o"],
            "Kbuild may only declare the inert kernel-shadow object")

    return {
        "schema": "aurum.adaptive-kernel.kernel-shadow-static-check.v1",
        "state": PASS_STATE,
        "candidate_id": manifest["candidate_id"],
        "basis": {
            "source_package_receipt_sha256": expected_receipt,
            "semantic_source_git_blob_sha1": actual_blob,
        },
        "source_sha256": sha256(source_path),
        "kbuild_sha256": sha256(kbuild_path),
        "manifest_sha256": sha256(manifest_path),
        "invariants": {
            "load_allowed": False,
            "successful_load_possible": False,
            "autoload_possible": False,
            "device_table_present": False,
            "driver_registration_present": False,
            "network_registration_present": False,
            "hardware_io_present": False,
            "usb_transfer_present": False,
            "register_write_present": False,
            "promotion_allowed": False,
            "write_authority": False,
        },
    }


def main() -> int:
    try:
        print(json.dumps(validate_candidate(), indent=2, sort_keys=True))
    except (ContractError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"state": "refused", "reason": str(exc)}, indent=2, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
