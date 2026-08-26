#!/usr/bin/env python3
"""Run a bounded headless QEMU boot and retain serial plus framebuffer proof."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path


DEFAULT_FORBIDDEN = (
    r"booting in blind mode",
    r"no suitable video mode",
    r"error:.*video mode",
    r"failed to start.*plymouth",
    r"failed to start.*graphical",
    r"drm.*\berror\b",
    r"gpu hang",
    r"failed to unload.*(?:drm|framebuffer|graphics|fbcon)",
)


def _ppm_metrics(path: Path) -> dict[str, int | str]:
    data = path.read_bytes()
    offset = 0

    def token() -> bytes:
        nonlocal offset
        while offset < len(data):
            if data[offset:offset + 1] == b"#":
                offset = data.find(b"\n", offset)
                if offset < 0:
                    raise ValueError("unterminated PPM comment")
            elif data[offset:offset + 1].isspace():
                offset += 1
            else:
                break
        start = offset
        while offset < len(data) and not data[offset:offset + 1].isspace():
            offset += 1
        return data[start:offset]

    if token() != b"P6":
        raise ValueError("QEMU screenshot is not a binary PPM")
    width = int(token())
    height = int(token())
    maximum = int(token())
    while offset < len(data) and data[offset:offset + 1].isspace():
        offset += 1
    pixels = data[offset:]
    if maximum != 255 or len(pixels) != width * height * 3:
        raise ValueError("QEMU screenshot dimensions do not match its payload")
    colors: set[bytes] = set()
    visible = 0
    for index in range(0, len(pixels), 3):
        value = pixels[index:index + 3]
        colors.add(value)
        if max(value) >= 24:
            visible += 1
    return {
        "width": width,
        "height": height,
        "unique_colors": len(colors),
        "visible_pixels": visible,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _hmp_screenshot(socket_path: Path, screenshot: Path) -> None:
    deadline = time.monotonic() + 10
    while True:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.connect(str(socket_path))
                client.settimeout(5)
                try:
                    client.recv(8192)
                except TimeoutError:
                    pass
                client.sendall(f"screendump {screenshot.resolve()}\n".encode())
                time.sleep(1)
                client.sendall(b"quit\n")
                return
        except (FileNotFoundError, ConnectionRefusedError, OSError):
            if time.monotonic() >= deadline:
                raise RuntimeError("QEMU monitor never became ready")
            time.sleep(0.25)


def _arguments(args: argparse.Namespace, monitor: Path) -> list[str]:
    qemu = shutil.which("qemu-system-x86_64")
    if not qemu:
        raise RuntimeError("qemu-system-x86_64 is unavailable")
    command = [
        qemu,
        "-m", "1024",
        "-smp", "2",
        "-nic", "user,model=e1000",
        "-display", "none",
        "-vga", "std",
        "-monitor", f"unix:{monitor},server=on,wait=off",
        "-serial", f"file:{args.log.resolve()}",
        "-no-reboot",
    ]
    if args.audio:
        command.extend([
            "-audiodev", "driver=none,id=aurum_audio",
            "-device", "intel-hda",
            "-device", "hda-duplex,audiodev=aurum_audio",
        ])
    if args.firmware == "uefi":
        if not args.ovmf_code or not args.ovmf_vars:
            raise ValueError("UEFI proof requires OVMF code and vars")
        command.extend([
            "-machine", "q35",
            "-drive", f"if=pflash,format=raw,readonly=on,file={args.ovmf_code.resolve()}",
            "-drive", f"if=pflash,format=raw,file={args.ovmf_vars.resolve()}",
            "-cdrom", str(args.iso.resolve()),
            "-boot", "d",
        ])
    elif args.firmware == "bios":
        command.extend(["-machine", "pc", "-cdrom", str(args.iso.resolve()), "-boot", "d"])
    else:
        if not args.kernel or not args.initrd or not args.append:
            raise ValueError("direct proof requires kernel, initrd and append arguments")
        command.extend([
            "-machine", "pc",
            "-cdrom", str(args.iso.resolve()),
            "-kernel", str(args.kernel.resolve()),
            "-initrd", str(args.initrd.resolve()),
            "-append", args.append,
        ])
    return command


def run(args: argparse.Namespace) -> dict[str, object]:
    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.screenshot.parent.mkdir(parents=True, exist_ok=True)
    args.log.unlink(missing_ok=True)
    args.screenshot.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"aurum-{args.name}-") as temporary:
        monitor = Path(temporary) / "monitor.sock"
        command = _arguments(args, monitor)
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        deadline = time.monotonic() + args.timeout
        observed = ""
        try:
            while time.monotonic() < deadline:
                if args.log.is_file():
                    observed = args.log.read_text(encoding="utf-8", errors="replace")
                if all(marker in observed for marker in args.require):
                    time.sleep(2)
                    _hmp_screenshot(monitor, args.screenshot)
                    break
                return_code = process.poll()
                if return_code is not None:
                    error = process.stderr.read() if process.stderr else ""
                    raise RuntimeError(f"QEMU exited before proof rc={return_code}: {error[-1000:]}")
                time.sleep(0.5)
            else:
                missing = [marker for marker in args.require if marker not in observed]
                raise RuntimeError(f"virtual boot timed out; missing markers: {missing}")
        except Exception:
            # Preserve the visible failure boundary even when Linux never
            # reaches serial output. Diagnostics must not die with the VM.
            if process.poll() is None and monitor.exists():
                try:
                    _hmp_screenshot(monitor, args.screenshot)
                except (OSError, RuntimeError):
                    pass
            raise
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    forbidden = [pattern for pattern in (*DEFAULT_FORBIDDEN, *args.forbid) if re.search(pattern, observed, re.I)]
    if forbidden:
        raise RuntimeError(f"forbidden graphics/boot evidence found: {forbidden}")
    metrics = _ppm_metrics(args.screenshot)
    if int(metrics["unique_colors"]) < args.min_colors:
        raise RuntimeError(f"framebuffer has too few colors: {metrics}")
    if int(metrics["visible_pixels"]) < args.min_visible_pixels:
        raise RuntimeError(f"framebuffer appears blank: {metrics}")
    receipt: dict[str, object] = {
        "schema": "aurum-tinyseed-virtual-boot-proof-v1",
        "name": args.name,
        "firmware": args.firmware,
        "required_markers": args.require,
        "forbidden_patterns": list(DEFAULT_FORBIDDEN) + args.forbid,
        "serial_sha256": hashlib.sha256(observed.encode()).hexdigest(),
        "framebuffer": metrics,
        "status": "verified",
    }
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return receipt


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--name", required=True)
    value.add_argument("--firmware", choices=("uefi", "bios", "direct"), required=True)
    value.add_argument("--iso", type=Path, required=True)
    value.add_argument("--log", type=Path, required=True)
    value.add_argument("--screenshot", type=Path, required=True)
    value.add_argument("--ovmf-code", type=Path)
    value.add_argument("--ovmf-vars", type=Path)
    value.add_argument("--kernel", type=Path)
    value.add_argument("--initrd", type=Path)
    value.add_argument("--append")
    value.add_argument("--audio", action="store_true")
    value.add_argument("--require", action="append", default=[])
    value.add_argument("--forbid", action="append", default=[])
    value.add_argument("--timeout", type=int, default=150)
    value.add_argument("--min-colors", type=int, default=4)
    value.add_argument("--min-visible-pixels", type=int, default=200)
    return value


def main() -> int:
    run(parser().parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
