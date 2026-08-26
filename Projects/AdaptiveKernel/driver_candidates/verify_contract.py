"""Static, fail-closed contract validation for inert driver candidates."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "candidate.json"
SOURCE = ROOT / "aurum_pi3_compile_probe.c"
KBUILD = ROOT / "Kbuild"


class ContractError(ValueError):
    """The candidate crossed or omitted a compile-only safety boundary."""


FORBIDDEN_SOURCE_PATTERNS = {
    "autoload alias": r"\bMODULE_ALIAS\s*\(",
    "autoload device table": r"\bMODULE_DEVICE_TABLE\s*\(",
    "module parameter": r"\bmodule_param(?:_named)?\s*\(",
    "module self-request": r"\brequest_module\s*\(",
    "dynamic kernel symbol lookup": r"\b(?:symbol_get|__symbol_get|kallsyms_lookup_name)\s*\(",
    "userspace execution": r"\bcall_usermodehelper\s*\(",
    "USB driver registration": r"\b(?:module_usb_driver|usb_register|usb_register_driver)\s*\(",
    "platform driver registration": r"\b(?:module_platform_driver|platform_driver_register)\s*\(",
    "PCI driver registration": r"\b(?:module_pci_driver|pci_register_driver)\s*\(",
    "network device registration": r"\b(?:register_netdev|register_netdevice)\s*\(",
    "driver or bus registration": r"\b(?:driver_register|bus_register)\s*\(",
    "driver binding": r"\b(?:device_bind_driver|driver_attach|device_driver_attach)\s*\(",
    "sysfs registration": r"\b(?:sysfs_create_file|device_create_file|class_create)\s*\(",
    "firmware request": r"\brequest_firmware(?:_direct|_into_buf|_nowait)?\s*\(",
    "USB hardware I/O": r"\b(?:usb_submit_urb|usb_control_msg|usb_bulk_msg)\s*\(",
    "memory-mapped hardware write": r"\b(?:writeb|writew|writel|writeq|iowrite8|iowrite16|iowrite32|iowrite64)\s*\(",
    "kernel file open": r"\bfilp_open\s*\(",
    "kernel file write": r"\bkernel_write\s*\(",
    "socket creation": r"\b(?:sock_create|sock_create_kern)\s*\(",
    "network carrier mutation": r"\bnetif_carrier_(?:on|off)\s*\(",
    "network device open": r"\bdev_open\s*\(",
    "network feature mutation": r"\b(?:netdev_update_features|dev_change_flags|dev_set_mtu)\s*\(",
    "boot or power transition": r"\b(?:kernel_restart|orderly_reboot|emergency_restart|machine_restart|kernel_power_off|orderly_poweroff)\s*\(",
    "module exit path": r"\bmodule_exit\s*\(",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), "candidate manifest must be one JSON object")
    return value


def validate_candidate(root: Path = ROOT) -> dict[str, Any]:
    manifest_path = root / MANIFEST.name
    source_path = root / SOURCE.name
    kbuild_path = root / KBUILD.name
    for path in (manifest_path, source_path, kbuild_path):
        _require(path.is_file(), f"required candidate file is missing: {path.name}")

    manifest = _load_manifest(manifest_path)
    _require(manifest.get("schema") == "aurum.adaptive-kernel.driver-candidate.v1", "unexpected manifest schema")
    target = manifest.get("target", {})
    build = manifest.get("build", {})
    safety = manifest.get("safety", {})
    _require(
        target.get("model_marker") == "Raspberry Pi 3 Model B Rev 1.2",
        "candidate target must remain exactly Raspberry Pi 3 Model B Rev 1.2",
    )
    _require(target.get("architecture") == "aarch64", "candidate must remain ARM64-only")
    _require(target.get("reference_driver") == "smsc95xx", "reference driver must remain explicit")
    _require(target.get("reference_driver_replaced") is False, "candidate must not replace smsc95xx")
    _require(target.get("exact_kernel_release_required") is True, "exact kernel release must be mandatory")
    _require(build.get("mode") == "compile-only", "candidate build mode must be compile-only")
    _require(build.get("kbuild_target") == "modules", "only the Kbuild modules target is allowed")
    _require(build.get("artifact_retained") is False, "compiled module artifacts must not be retained")
    inspection = build.get("artifact_inspection", {})
    _require(inspection.get("tools_required_in_ci") is True, "CI artifact inspection tools must be required")
    _require(inspection.get("exact_vermagic_required") is True, "exact vermagic inspection must be required")
    for key in (
        "module_aliases_allowed",
        "device_table_symbols_allowed",
        "forbidden_unresolved_capability_symbols_allowed",
    ):
        _require(inspection.get(key) is False, f"build.artifact_inspection.{key} must be false")

    required_false = (
        "load_allowed",
        "successful_load_possible",
        "registers_device_driver",
        "registers_network_device",
        "registers_sysfs_interface",
        "performs_hardware_io",
        "changes_driver_binding",
        "changes_firmware",
        "changes_boot_configuration",
        "changes_network_configuration",
        "self_loads_or_requests_modules",
        "production_nodes_allowed",
    )
    for key in required_false:
        _require(safety.get(key) is False, f"safety.{key} must be false")
    _require(safety.get("init_behavior") == "return-negative-eperm", "module init must refuse loading")
    _require(safety.get("autoload_aliases") == [], "autoload aliases must stay empty")

    source = source_path.read_text(encoding="utf-8")
    for label, pattern in FORBIDDEN_SOURCE_PATTERNS.items():
        _require(re.search(pattern, source) is None, f"forbidden candidate capability: {label}")
    inert_init = re.compile(
        r"static\s+int\s+__init\s+aurum_pi3_compile_probe_init\s*\(\s*void\s*\)"
        r"\s*\{\s*return\s+-EPERM\s*;\s*\}",
        re.MULTILINE,
    )
    _require(inert_init.search(source) is not None, "init function must contain only return -EPERM")
    _require(
        source.count("module_init(aurum_pi3_compile_probe_init);") == 1,
        "exactly one inert module init declaration is required",
    )
    for evidence_token in (
        "struct sk_buff",
        "struct urb",
        "netdev_features_t",
        "struct usb_device_descriptor",
    ):
        _require(evidence_token in source, f"compile evidence surface is missing: {evidence_token}")

    kbuild_lines = [
        line.strip()
        for line in kbuild_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    _require(kbuild_lines == ["obj-m := aurum_pi3_compile_probe.o"], "Kbuild may only declare the inert object")

    return {
        "schema": "aurum.adaptive-kernel.driver-candidate-static-check.v1",
        "state": "verified-inert-compile-only",
        "candidate_id": manifest["candidate_id"],
        "target_model_marker": target["model_marker"],
        "source_sha256": _sha256(source_path),
        "kbuild_sha256": _sha256(kbuild_path),
        "manifest_sha256": _sha256(manifest_path),
        "invariants": {
            "exact_kernel_release_required": True,
            "artifact_inspection_required_in_ci": True,
            "load_allowed": False,
            "successful_load_possible": False,
            "autoload_possible": False,
            "driver_registration_present": False,
            "network_registration_present": False,
            "sysfs_registration_present": False,
            "hardware_io_present": False,
            "firmware_boot_network_mutation_present": False,
            "artifact_retained": False,
        },
    }


def main() -> int:
    try:
        print(json.dumps(validate_candidate(), indent=2, sort_keys=True))
    except (ContractError, json.JSONDecodeError) as exc:
        print(json.dumps({"state": "refused", "reason": str(exc)}, indent=2, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
