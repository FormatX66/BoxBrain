"""Compile an inert candidate against one exact ARM64 kernel header tree."""

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
from typing import Any, Callable

from verify_contract import KBUILD, MANIFEST, ROOT, SOURCE, validate_candidate


RELEASE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+~-]{0,127}$")
Runner = Callable[..., subprocess.CompletedProcess[str]]
ToolResolver = Callable[[str], str | None]
MAX_TOOL_OUTPUT = 4000
MAX_RECORDED_SYMBOLS = 128
FORBIDDEN_UNRESOLVED_SYMBOL = re.compile(
    r"^(?:"
    r"__request_module|request_module|call_usermodehelper|kallsyms_lookup_name|__symbol_get|"
    r"usb_register_driver|usb_submit_urb|usb_control_msg|usb_bulk_msg|"
    r"platform_driver_register|pci_register_driver|driver_register|bus_register|"
    r"device_bind_driver|driver_attach|device_driver_attach|"
    r"register_netdev|register_netdevice|sysfs_create_file|device_create_file|__class_create|class_create|"
    r"request_firmware(?:_direct|_into_buf|_nowait)?|filp_open|kernel_write|"
    r"sock_create|sock_create_kern|netif_carrier_on|netif_carrier_off|dev_open|"
    r"netdev_update_features|dev_change_flags|dev_set_mtu|"
    r"kernel_restart|orderly_reboot|emergency_restart|machine_restart|kernel_power_off|orderly_poweroff|"
    r"writeb|writew|writel|writeq|iowrite8|iowrite16|iowrite32|iowrite64"
    r")$"
)


class CompileRefusal(ValueError):
    """The supplied header tree cannot prove the exact compile target."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_kernel_build(kernel_build: Path, expected_release: str) -> dict[str, Any]:
    if not RELEASE_PATTERN.fullmatch(expected_release):
        raise CompileRefusal("expected kernel release is empty or unsafe")
    root = kernel_build.resolve(strict=True)
    required = {
        "makefile": root / "Makefile",
        "config": root / ".config",
        "module_symvers": root / "Module.symvers",
        "kernel_release": root / "include" / "config" / "kernel.release",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if missing:
        raise CompileRefusal(f"exact header tree is incomplete: {', '.join(sorted(missing))}")
    recorded_release = required["kernel_release"].read_text(encoding="utf-8").strip()
    if recorded_release != expected_release:
        raise CompileRefusal(
            f"kernel release mismatch: expected {expected_release!r}, header tree records {recorded_release!r}"
        )
    config = required["config"].read_text(encoding="utf-8", errors="replace")
    if not re.search(r"(?m)^CONFIG_ARM64=y$", config):
        raise CompileRefusal("header tree does not prove CONFIG_ARM64=y")
    return {
        "path": str(root),
        "kernel_release": recorded_release,
        "architecture": "arm64",
        "makefile_sha256": _sha256(required["makefile"]),
        "config_sha256": _sha256(required["config"]),
        "module_symvers_sha256": _sha256(required["module_symvers"]),
    }


def build_command(kernel_build: Path, module_root: Path) -> list[str]:
    return [
        "make",
        "-s",
        "-C",
        str(kernel_build),
        f"M={module_root}",
        "ARCH=arm64",
        "modules",
    ]


def _resolve_first(tool_resolver: ToolResolver, names: list[str]) -> str | None:
    for name in names:
        resolved = tool_resolver(name)
        if resolved:
            return resolved
    return None


def _run_read_only_tool(
    *,
    label: str,
    command: list[str],
    runner: Runner,
    timeout_seconds: int,
) -> tuple[dict[str, Any], str]:
    completed = runner(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout_seconds,
    )
    output = completed.stdout or ""
    return (
        {
            "label": label,
            "tool": command[0],
            "arguments": command[1:-1],
            "exit_code": int(completed.returncode),
            "output": output[:MAX_TOOL_OUTPUT],
            "output_truncated": len(output) > MAX_TOOL_OUTPUT,
        },
        output,
    )


def _posix_nm_symbols(output: str) -> list[str]:
    symbols: list[str] = []
    for line in output.splitlines():
        fields = line.strip().split()
        if not fields:
            continue
        candidate = fields[0]
        if re.fullmatch(r"[A-Za-z_.$][A-Za-z0-9_.$@-]*", candidate):
            symbols.append(candidate.split("@", 1)[0])
    return sorted(set(symbols))


def inspect_module_artifact(
    module: Path,
    expected_release: str,
    *,
    cross_compile: str = "",
    runner: Runner = subprocess.run,
    tool_resolver: ToolResolver = shutil.which,
    tools_required: bool = True,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Inspect one temporary module with read-only metadata/symbol tools."""

    modinfo = _resolve_first(tool_resolver, ["modinfo"])
    nm_names = [f"{cross_compile}nm"] if cross_compile else []
    nm_names.extend(["llvm-nm", "nm"])
    nm = _resolve_first(tool_resolver, nm_names)
    missing = [name for name, value in (("modinfo", modinfo), ("nm", nm)) if not value]
    receipt: dict[str, Any] = {
        "state": "inspecting",
        "tools_required": tools_required,
        "tools": {"modinfo": modinfo, "nm": nm},
        "missing_tools": missing,
        "exact_vermagic": False,
        "vermagic": None,
        "vermagic_architecture": None,
        "aliases": [],
        "device_table_symbols": [],
        "unresolved_symbol_count": 0,
        "unresolved_symbols": [],
        "unresolved_symbols_truncated": False,
        "forbidden_unresolved_symbols": [],
        "tool_runs": [],
    }
    if missing:
        receipt["state"] = "held-artifact-inspection-tools-unavailable"
        return receipt

    runs: list[dict[str, Any]] = []
    vermagic_run, vermagic_output = _run_read_only_tool(
        label="vermagic",
        command=[str(modinfo), "-F", "vermagic", str(module)],
        runner=runner,
        timeout_seconds=timeout_seconds,
    )
    runs.append(vermagic_run)
    aliases_run, aliases_output = _run_read_only_tool(
        label="aliases",
        command=[str(modinfo), "-F", "alias", str(module)],
        runner=runner,
        timeout_seconds=timeout_seconds,
    )
    runs.append(aliases_run)
    symbols_run, symbols_output = _run_read_only_tool(
        label="all-symbols",
        command=[str(nm), "--format=posix", str(module)],
        runner=runner,
        timeout_seconds=timeout_seconds,
    )
    runs.append(symbols_run)
    unresolved_run, unresolved_output = _run_read_only_tool(
        label="undefined-symbols",
        command=[str(nm), "--undefined-only", "--format=posix", str(module)],
        runner=runner,
        timeout_seconds=timeout_seconds,
    )
    runs.append(unresolved_run)
    receipt["tool_runs"] = runs

    vermagic_lines = [line.strip() for line in vermagic_output.splitlines() if line.strip()]
    vermagic = vermagic_lines[0][:512] if len(vermagic_lines) == 1 else None
    vermagic_release = vermagic.split()[0] if vermagic else None
    vermagic_architecture = "aarch64" if vermagic and "aarch64" in vermagic.split() else None
    aliases = [line.strip()[:512] for line in aliases_output.splitlines() if line.strip()]
    symbols = _posix_nm_symbols(symbols_output)
    unresolved = _posix_nm_symbols(unresolved_output)
    device_tables = [symbol for symbol in symbols if "device_table" in symbol]
    forbidden = [symbol for symbol in unresolved if FORBIDDEN_UNRESOLVED_SYMBOL.fullmatch(symbol)]
    receipt.update(
        {
            "vermagic": vermagic,
            "vermagic_release": vermagic_release,
            "vermagic_architecture": vermagic_architecture,
            "exact_vermagic": vermagic_release == expected_release and vermagic_architecture == "aarch64",
            "aliases": aliases[:64],
            "aliases_truncated": len(aliases) > 64,
            "device_table_symbols": device_tables[:MAX_RECORDED_SYMBOLS],
            "device_table_symbols_truncated": len(device_tables) > MAX_RECORDED_SYMBOLS,
            "unresolved_symbol_count": len(unresolved),
            "unresolved_symbols": unresolved[:MAX_RECORDED_SYMBOLS],
            "unresolved_symbols_truncated": len(unresolved) > MAX_RECORDED_SYMBOLS,
            "forbidden_unresolved_symbols": forbidden[:MAX_RECORDED_SYMBOLS],
        }
    )

    if any(run["exit_code"] != 0 for run in runs):
        receipt["state"] = "failed-artifact-inspection-tool"
    elif not receipt["exact_vermagic"]:
        receipt["state"] = "failed-exact-vermagic"
    elif aliases:
        receipt["state"] = "failed-module-alias-present"
    elif device_tables:
        receipt["state"] = "failed-device-table-present"
    elif forbidden:
        receipt["state"] = "failed-forbidden-unresolved-symbol"
    else:
        receipt["state"] = "verified-inert-artifact"
    return receipt


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def compile_candidate(
    *,
    kernel_build: Path,
    expected_release: str,
    receipt_path: Path,
    cross_compile: str = "",
    timeout_seconds: int = 300,
    runner: Runner = subprocess.run,
    tool_resolver: ToolResolver = shutil.which,
    artifact_tools_required: bool = True,
) -> dict[str, Any]:
    static_receipt = validate_candidate(ROOT)
    header_receipt = validate_kernel_build(kernel_build, expected_release)
    if timeout_seconds < 1 or timeout_seconds > 900:
        raise CompileRefusal("compile timeout must be between 1 and 900 seconds")
    if cross_compile and not re.fullmatch(r"[A-Za-z0-9_./+~-]+", cross_compile):
        raise CompileRefusal("cross-compiler prefix contains unsafe characters")

    receipt: dict[str, Any] = {
        "schema": "aurum.adaptive-kernel.compile-only-receipt.v1",
        "state": "compiling",
        "candidate_id": static_receipt["candidate_id"],
        "candidate_contract": static_receipt,
        "kernel_headers": header_receipt,
        "build": {
            "target": "modules",
            "architecture": "arm64",
            "cross_compile": cross_compile or None,
            "loader_invoked": False,
            "installer_invoked": False,
            "artifact_retained": False,
        },
        "authority": {
            "load_allowed": False,
            "driver_binding_change_allowed": False,
            "firmware_mutation_allowed": False,
            "boot_mutation_allowed": False,
            "network_mutation_allowed": False,
        },
    }

    with tempfile.TemporaryDirectory(prefix="aurum-pi3-compile-only-") as temporary:
        module_root = Path(temporary)
        for source in (SOURCE, KBUILD, MANIFEST):
            shutil.copy2(source, module_root / source.name)
        command = build_command(Path(header_receipt["path"]), module_root)
        environment = os.environ.copy()
        environment.update(
            {
                "ARCH": "arm64",
                "KBUILD_BUILD_USER": "aurum-compile-only",
                "KBUILD_BUILD_HOST": "offline-ci",
            }
        )
        if cross_compile:
            environment["CROSS_COMPILE"] = cross_compile
        completed = runner(
            command,
            check=False,
            cwd=module_root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_seconds,
        )
        output = (completed.stdout or "")[-4000:]
        receipt["build"]["command"] = command
        receipt["build"]["exit_code"] = int(completed.returncode)
        receipt["build"]["bounded_output"] = output
        module = module_root / "aurum_pi3_compile_probe.ko"
        if completed.returncode != 0:
            receipt["state"] = "failed-compile"
        elif not module.is_file() or module.stat().st_size <= 0:
            receipt["state"] = "failed-artifact-missing"
        else:
            body = module.read_bytes()
            release_embedded = expected_release.encode("utf-8") in body
            receipt["build"]["module_size_bytes"] = len(body)
            receipt["build"]["module_sha256"] = hashlib.sha256(body).hexdigest()
            receipt["build"]["expected_release_embedded"] = release_embedded
            inspection = inspect_module_artifact(
                module,
                expected_release,
                cross_compile=cross_compile,
                runner=runner,
                tool_resolver=tool_resolver,
                tools_required=artifact_tools_required,
                timeout_seconds=min(timeout_seconds, 60),
            )
            receipt["artifact_inspection"] = inspection
            if not release_embedded:
                receipt["state"] = "failed-vermagic-release-proof"
            elif inspection["state"] == "verified-inert-artifact":
                receipt["state"] = "verified-compile-only"
            else:
                receipt["state"] = inspection["state"]

        receipt["build"]["artifact_inspection_recorded_before_artifact_removal"] = (
            "artifact_inspection" in receipt
        )
        receipt["build"]["temporary_build_removed"] = False
        _write_receipt(receipt_path, receipt)

    receipt["build"]["temporary_build_removed"] = True
    _write_receipt(receipt_path, receipt)
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel-build", required=True, type=Path)
    parser.add_argument("--expected-kernel-release", required=True)
    parser.add_argument("--cross-compile", default="")
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument(
        "--allow-missing-artifact-tools",
        action="store_true",
        help="compile portably but hold verification if modinfo or nm is unavailable",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        receipt = compile_candidate(
            kernel_build=args.kernel_build,
            expected_release=args.expected_kernel_release,
            receipt_path=args.receipt,
            cross_compile=args.cross_compile,
            timeout_seconds=args.timeout_seconds,
            artifact_tools_required=not args.allow_missing_artifact_tools,
        )
    except (CompileRefusal, OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError) as exc:
        receipt = {
            "schema": "aurum.adaptive-kernel.compile-only-receipt.v1",
            "state": "refused",
            "reason": str(exc),
        }
        _write_receipt(args.receipt, receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt.get("state") == "verified-compile-only" else 1


if __name__ == "__main__":
    raise SystemExit(main())
