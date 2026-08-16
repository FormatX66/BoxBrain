"""Live emulator-only UART probe for Aurum driver differential verification.

This helper launches QEMU paused and uses the Human Monitor Protocol I/O-port
commands to observe the emulated 16550-compatible UART. All writes target only
QEMU's emulated device. No host physical I/O, device files, MMIO mappings,
firmware, or persistent hardware are touched.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

PROBE_SCHEMA = "aurum.driver.emulator-uart-probe.v0"
_PORT_READ_RE = re.compile(r"portb\[(0x[0-9a-fA-F]+)\]\s*=\s*(0x[0-9a-fA-F]+)")

_BASE_PORT = 0x3F8
_SELECTORS = {
    "receiver_or_transmit_or_divisor_lsb": 0,
    "interrupt_enable_or_divisor_msb": 1,
    "line_control": 3,
    "modem_control": 4,
    "line_status": 5,
}


def _read_command(selector: int) -> str:
    return f"i /b 0x{_BASE_PORT + selector:x}"


def _write_command(selector: int, value: int) -> str:
    return f"o /b 0x{_BASE_PORT + selector:x} 0x{value:02x}"


def parse_monitor_reads(output: str) -> list[dict[str, int]]:
    if not isinstance(output, str):
        raise ValueError("monitor output must be text")
    return [
        {"port": int(match.group(1), 16), "value": int(match.group(2), 16) & 0xFF}
        for match in _PORT_READ_RE.finditer(output)
    ]


def run_qemu_uart_probe(qemu_executable: str = "qemu-system-x86_64") -> dict[str, Any]:
    """Run bounded DLAB and TX/RX-loopback probes against QEMU's UART only."""

    resolved = shutil.which(qemu_executable)
    if resolved is None:
        raise RuntimeError(f"QEMU executable not found: {qemu_executable}")

    version = subprocess.run(
        [resolved, "--version"], text=True, capture_output=True, check=True, timeout=10
    ).stdout.splitlines()[0].strip()

    data_selector = _SELECTORS["receiver_or_transmit_or_divisor_lsb"]
    commands = [
        # Reset/bank-selection parity.
        _read_command(_SELECTORS["line_status"]),
        _read_command(_SELECTORS["line_control"]),
        _write_command(_SELECTORS["line_control"], 0x80),
        _read_command(_SELECTORS["line_control"]),
        _write_command(data_selector, 0x34),
        _write_command(_SELECTORS["interrupt_enable_or_divisor_msb"], 0x12),
        _read_command(data_selector),
        _read_command(_SELECTORS["interrupt_enable_or_divisor_msb"]),
        _write_command(_SELECTORS["line_control"], 0x00),
        _read_command(_SELECTORS["line_control"]),
        _read_command(_SELECTORS["interrupt_enable_or_divisor_msb"]),
        # Emulator-internal TX -> RX proof. MCR LOOP disconnects external SIN and
        # feeds the transmitter shift path into the receiver shift path.
        _read_command(_SELECTORS["modem_control"]),
        _write_command(_SELECTORS["modem_control"], 0x10),
        _read_command(_SELECTORS["modem_control"]),
        _write_command(data_selector, 0xA5),
        _read_command(_SELECTORS["line_status"]),
        _read_command(data_selector),
        _read_command(_SELECTORS["line_status"]),
        _write_command(_SELECTORS["modem_control"], 0x00),
        _read_command(_SELECTORS["modem_control"]),
        "quit",
    ]

    proc = subprocess.run(
        [
            resolved, "-machine", "pc", "-nodefaults", "-display", "none", "-S",
            "-monitor", "stdio", "-serial", "null", "-no-reboot", "-no-shutdown",
        ],
        input="\n".join(commands) + "\n",
        text=True,
        capture_output=True,
        timeout=20,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"QEMU monitor probe failed with rc={proc.returncode}: {proc.stderr[-2000:]}")

    reads = parse_monitor_reads(proc.stdout)
    names = [
        "line_status_reset",
        "line_control_reset",
        "line_control_dlab_set",
        "divisor_lsb_readback",
        "divisor_msb_readback",
        "line_control_dlab_cleared",
        "interrupt_enable_after_bank_restore",
        "modem_control_before_loop",
        "modem_control_loop_set",
        "line_status_after_loopback_transmit",
        "receiver_buffer_loopback_read",
        "line_status_after_loopback_drain",
        "modem_control_loop_cleared",
    ]
    if len(reads) != len(names):
        raise RuntimeError(
            f"unexpected QEMU monitor read count: expected {len(names)}, got {len(reads)}; "
            f"output={proc.stdout[-3000:]}"
        )

    observations = {
        name: {"port": read["port"], "value": read["value"]}
        for name, read in zip(names, reads, strict=True)
    }
    return {
        "schema": PROBE_SCHEMA,
        "origin": "qemu-hmp-live",
        "emulator": "qemu-system-x86_64",
        "emulator_version": version,
        "physical_hardware_observation": False,
        "emulator_execution_observed": True,
        "base_port": _BASE_PORT,
        "selector_offsets": dict(_SELECTORS),
        "test_pattern": {
            "divisor_lsb": 0x34,
            "divisor_msb": 0x12,
            "dlab_mask": 0x80,
            "loop_mask": 0x10,
            "loopback_data": 0xA5,
        },
        "observations": observations,
        "safety": {
            "host_physical_io_performed": False,
            "host_device_file_io_performed": False,
            "physical_writes_performed": False,
            "firmware_changes_performed": False,
            "emulated_io_port_reads_performed": True,
            "emulated_io_port_writes_performed": True,
            "qemu_process_only": True,
            "external_serial_backend_data_path_used": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--qemu", default="qemu-system-x86_64")
    args = parser.parse_args()
    result = run_qemu_uart_probe(args.qemu)
    text = json.dumps(result, sort_keys=True, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
