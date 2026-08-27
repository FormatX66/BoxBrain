"""Compile and inspect the inert Pi3 smsc95xx kernel-shaped shadow candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "aurum_pi3_smsc95xx_kernel_shadow.c"
KBUILD = ROOT / "Kbuild"
MODULE_NAME = "aurum_pi3_smsc95xx_kernel_shadow.ko"
PASS_STATIC = "verified-inert-kernel-shadow-compile-only"
PASS_COMPILE = "verified-kernel-shadow-compile-only"
RELEASE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+~-]{0,127}$")
FORBIDDEN_UNRESOLVED = re.compile(
    r"^(?:__request_module|request_module|call_usermodehelper|kallsyms_lookup_name|__symbol_get|"
    r"usb_register_driver|usb_submit_urb|usb_control_msg|usb_bulk_msg|usb_clear_halt|"
    r"register_netdev|register_netdevice|driver_register|device_bind_driver|driver_attach|"
    r"request_firmware|request_firmware_direct|request_firmware_nowait|"
    r"netif_carrier_on|netif_carrier_off|netdev_update_features|dev_change_flags|dev_set_mtu|"
    r"writeb|writew|writel|writeq|iowrite8|iowrite16|iowrite32|iowrite64)$"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_kernel_build(root: Path, expected_release: str) -> dict[str, Any]:
    if not RELEASE_RE.fullmatch(expected_release):
        raise ValueError("expected kernel release is unsafe")
    root = root.resolve(strict=True)
    required = {
        "makefile": root / "Makefile",
        "config": root / ".config",
        "module_symvers": root / "Module.symvers",
        "kernel_release": root / "include" / "config" / "kernel.release",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if missing:
        raise ValueError("exact kernel header tree incomplete: " + ", ".join(sorted(missing)))
    release = required["kernel_release"].read_text(encoding="utf-8").strip()
    if release != expected_release:
        raise ValueError(f"kernel header release mismatch: {release!r}")
    config = required["config"].read_text(encoding="utf-8", errors="replace")
    if not re.search(r"(?m)^CONFIG_ARM64=y$", config):
        raise ValueError("kernel header tree does not prove CONFIG_ARM64=y")
    return {
        "path": str(root),
        "kernel_release": release,
        "architecture": "arm64",
        "makefile_sha256": sha256(required["makefile"]),
        "config_sha256": sha256(required["config"]),
        "module_symvers_sha256": sha256(required["module_symvers"]),
    }


def parse_symbols(output: str) -> list[str]:
    values: set[str] = set()
    for line in output.splitlines():
        fields = line.strip().split()
        if fields and re.fullmatch(r"[A-Za-z_.$][A-Za-z0-9_.$@-]*", fields[0]):
            values.add(fields[0].split("@", 1)[0])
    return sorted(values)


def extract_modinfo_values(data: bytes, key: str) -> list[str]:
    """Read NUL-terminated MODULE_INFO values directly from a module image.

    `modinfo` is only a presentation tool over the module's .modinfo strings.  Some
    minimal Pi images intentionally omit the kmod userspace package even though
    the kernel build toolchain is complete.  Reading the exact immutable artifact
    bytes keeps this proof read-only and avoids installing software on the Pi.
    The scan is conservative: malformed/non-UTF8 values are ignored and duplicate
    values are collapsed, while any discovered alias still fails the caller's gate.
    """
    if not re.fullmatch(r"[A-Za-z0-9_]+", key):
        raise ValueError("unsafe modinfo key")
    prefix = key.encode("ascii") + b"="
    values: set[str] = set()
    for match in re.finditer(re.escape(prefix) + rb"([^\x00\r\n]{1,1024})\x00", data):
        try:
            value = match.group(1).decode("utf-8", errors="strict").strip()
        except UnicodeDecodeError:
            continue
        if value:
            values.add(value)
    return sorted(values)


def run_capture(command: list[str], *, cwd: Path | None = None, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, check=False, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, timeout=timeout)


def compile_shadow(*, kernel_build: Path, expected_release: str, static_receipt: Path,
                   receipt_path: Path, timeout_seconds: int = 300) -> dict[str, Any]:
    static = json.loads(static_receipt.read_text(encoding="utf-8-sig"))
    if static.get("state") != PASS_STATIC:
        raise ValueError("static kernel-shadow contract has not passed")
    if static.get("candidate_id") != "pi3-smsc95xx-kernel-shadow-compile-v1":
        raise ValueError("static kernel-shadow candidate identity moved")
    if static.get("source_sha256") != sha256(SOURCE):
        raise ValueError("transferred kernel-shadow source differs from static proof")
    if static.get("kbuild_sha256") != sha256(KBUILD):
        raise ValueError("transferred Kbuild differs from static proof")
    invariants = static.get("invariants") or {}
    if not invariants or any(value is not False for value in invariants.values()):
        raise ValueError("static kernel-shadow contract unexpectedly grants capability")
    if timeout_seconds < 1 or timeout_seconds > 900:
        raise ValueError("compile timeout must be between 1 and 900 seconds")

    headers = validate_kernel_build(kernel_build, expected_release)
    receipt: dict[str, Any] = {
        "schema": "aurum.adaptive-kernel.kernel-shadow-compile-receipt.v1",
        "state": "compiling",
        "candidate_id": static["candidate_id"],
        "static_contract": static,
        "kernel_headers": headers,
        "build": {
            "target": "modules", "architecture": "arm64", "loader_invoked": False,
            "installer_invoked": False, "artifact_retained": False,
        },
        "authority": {
            "load_allowed": False, "driver_binding_change_allowed": False,
            "usb_transfer_allowed": False, "register_write_allowed": False,
            "firmware_mutation_allowed": False, "network_mutation_allowed": False,
            "promotion_allowed": False, "write_authority": False,
        },
    }

    with tempfile.TemporaryDirectory(prefix="aurum-pi3-kernel-shadow-") as temp:
        build_root = Path(temp)
        shutil.copy2(SOURCE, build_root / SOURCE.name)
        shutil.copy2(KBUILD, build_root / KBUILD.name)
        command = ["make", "-s", "-C", str(headers["path"]), f"M={build_root}", "ARCH=arm64", "modules"]
        env = os.environ.copy()
        env.update({"ARCH": "arm64", "KBUILD_BUILD_USER": "aurum-kernel-shadow", "KBUILD_BUILD_HOST": "compile-only"})
        completed = subprocess.run(command, cwd=build_root, env=env, check=False,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, timeout=timeout_seconds)
        receipt["build"]["command"] = command
        receipt["build"]["exit_code"] = int(completed.returncode)
        receipt["build"]["bounded_output"] = (completed.stdout or "")[-4000:]
        module = build_root / MODULE_NAME
        if completed.returncode != 0:
            receipt["state"] = "failed-compile"
        elif not module.is_file() or module.stat().st_size <= 0:
            receipt["state"] = "failed-artifact-missing"
        else:
            nm = shutil.which("nm") or shutil.which("llvm-nm")
            if not nm:
                receipt["state"] = "held-symbol-inspection-tool-unavailable"
            else:
                module_bytes = module.read_bytes()
                vermagic_values = extract_modinfo_values(module_bytes, "vermagic")
                aliases = extract_modinfo_values(module_bytes, "alias")
                all_symbols_run = run_capture([nm, "--format=posix", str(module)])
                undefined_run = run_capture([nm, "--undefined-only", "--format=posix", str(module)])
                runs = (all_symbols_run, undefined_run)
                if any(item.returncode != 0 for item in runs):
                    receipt["state"] = "failed-artifact-inspection-tool"
                else:
                    vermagic = vermagic_values[0] if len(vermagic_values) == 1 else ""
                    all_symbols = parse_symbols(all_symbols_run.stdout)
                    undefined = parse_symbols(undefined_run.stdout)
                    device_tables = [name for name in all_symbols if "device_table" in name]
                    forbidden = [name for name in undefined if FORBIDDEN_UNRESOLVED.fullmatch(name)]
                    exact_vermagic = bool(vermagic) and vermagic.split()[0] == expected_release and "aarch64" in vermagic.split()
                    receipt["artifact_inspection"] = {
                        "modinfo_reader": "artifact-bytes",
                        "vermagic": vermagic,
                        "vermagic_values": vermagic_values,
                        "exact_vermagic": exact_vermagic,
                        "aliases": aliases,
                        "device_table_symbols": device_tables,
                        "undefined_symbol_count": len(undefined),
                        "undefined_symbols": undefined[:128],
                        "forbidden_unresolved_symbols": forbidden,
                    }
                    receipt["build"]["module_size_bytes"] = module.stat().st_size
                    receipt["build"]["module_sha256"] = hashlib.sha256(module_bytes).hexdigest()
                    receipt["build"]["expected_release_embedded"] = expected_release.encode() in module_bytes
                    if not exact_vermagic or not receipt["build"]["expected_release_embedded"]:
                        receipt["state"] = "failed-exact-vermagic"
                    elif aliases:
                        receipt["state"] = "failed-module-alias-present"
                    elif device_tables:
                        receipt["state"] = "failed-device-table-present"
                    elif forbidden:
                        receipt["state"] = "failed-forbidden-unresolved-symbol"
                    else:
                        receipt["state"] = PASS_COMPILE
        receipt["build"]["artifact_inspection_recorded_before_removal"] = "artifact_inspection" in receipt
        receipt["build"]["temporary_build_removed"] = False
        write_json(receipt_path, receipt)

    receipt["build"]["temporary_build_removed"] = True
    write_json(receipt_path, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel-build", required=True, type=Path)
    parser.add_argument("--expected-kernel-release", required=True)
    parser.add_argument("--static-receipt", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args()
    try:
        result = compile_shadow(kernel_build=args.kernel_build, expected_release=args.expected_kernel_release,
                                static_receipt=args.static_receipt, receipt_path=args.receipt,
                                timeout_seconds=args.timeout_seconds)
    except (ValueError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        result = {
            "schema": "aurum.adaptive-kernel.kernel-shadow-compile-receipt.v1",
            "state": "refused", "reason": str(exc),
            "authority": {"load_allowed": False, "driver_binding_change_allowed": False,
                          "usb_transfer_allowed": False, "register_write_allowed": False,
                          "promotion_allowed": False, "write_authority": False},
        }
        write_json(args.receipt, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("state") == PASS_COMPILE else 2


if __name__ == "__main__":
    raise SystemExit(main())
