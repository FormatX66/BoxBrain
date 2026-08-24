#!/usr/bin/env python3
"""Small guarded installer used by the Aurum Tiny Seed.

The Tiny Seed installs only a minimal, known bootable germ substrate. It then
asks the germ to regrow the current trusted Aurum genetics inside the target
before first boot when the platform adapter supports local A/B growth.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence

MIN_BYTES = 8 * 1024**3
SAFE_DEVICE = re.compile(r"/dev/(?:nvme\d+n\d+|sd[a-z]+|mmcblk\d+|vd[a-z]+)")


class InstallError(RuntimeError):
    pass


def _run(args: Sequence[str], *, timeout: int = 300, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            list(args),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise InstallError(f"command failed to start: {exc}") from exc
    if check and result.returncode != 0:
        raise InstallError((result.stdout or "command failed").strip()[-2000:])
    return result


def _partition(device: str, number: int) -> Path:
    suffix = "p" if device[-1:].isdigit() else ""
    return Path(f"{device}{suffix}{number}")


def _boot_disk() -> str | None:
    findmnt = shutil.which("findmnt")
    lsblk = shutil.which("lsblk")
    if not findmnt or not lsblk:
        return None
    for mountpoint in ("/run/live/medium", "/boot/firmware", "/"):
        if not Path(mountpoint).exists():
            continue
        source = _run([findmnt, "-n", "-o", "SOURCE", "--target", mountpoint], timeout=10, check=False).stdout.strip()
        if not source.startswith("/dev/"):
            continue
        pkname = _run([lsblk, "-n", "-o", "PKNAME", source], timeout=10, check=False).stdout.strip()
        return f"/dev/{pkname}" if pkname else source
    return None


def _mountpoints(record: dict[str, Any]) -> list[str]:
    values: list[str] = []
    raw = record.get("mountpoints")
    if isinstance(raw, list):
        values.extend(str(x) for x in raw if x)
    elif isinstance(raw, str) and raw:
        values.append(raw)
    if record.get("mountpoint"):
        values.append(str(record["mountpoint"]))
    for child in record.get("children") or []:
        if isinstance(child, dict):
            values.extend(_mountpoints(child))
    return values


def _confirmation(device: str, serial: str, size: int) -> str:
    raw = json.dumps({"device": device, "serial": serial, "size": size}, sort_keys=True).encode()
    return "ERASE-" + hashlib.sha256(raw).hexdigest()[:8].upper()


def discover_targets() -> list[dict[str, Any]]:
    lsblk = shutil.which("lsblk")
    if not lsblk:
        raise InstallError("lsblk is unavailable")
    result = _run(
        [
            lsblk,
            "--json",
            "--bytes",
            "--paths",
            "--output",
            "NAME,PATH,TYPE,SIZE,MODEL,SERIAL,TRAN,RM,RO,HOTPLUG,MOUNTPOINTS",
        ],
        timeout=20,
    )
    try:
        devices = json.loads(result.stdout).get("blockdevices") or []
    except json.JSONDecodeError as exc:
        raise InstallError("disk inventory was not valid JSON") from exc
    boot = _boot_disk()
    targets: list[dict[str, Any]] = []
    for record in devices:
        if not isinstance(record, dict) or record.get("type") != "disk":
            continue
        device = str(record.get("path") or record.get("name") or "")
        size = int(record.get("size") or 0)
        if not SAFE_DEVICE.fullmatch(device) or size < MIN_BYTES or bool(record.get("ro")):
            continue
        if boot and device == boot:
            continue
        if _mountpoints(record):
            continue
        serial = " ".join(str(record.get("serial") or "serial-unavailable").split())[:128]
        targets.append(
            {
                "device": device,
                "model": " ".join(str(record.get("model") or "unknown").split())[:128],
                "serial": serial,
                "size_bytes": size,
                "size_gib": round(size / 1024**3, 1),
                "transport": str(record.get("tran") or ""),
                "removable": bool(record.get("rm")) or bool(record.get("hotplug")),
                "confirmation_code": _confirmation(device, serial, size),
            }
        )
    return sorted(targets, key=lambda x: x["device"])


def plan() -> dict[str, Any]:
    targets = discover_targets()
    return {
        "schema": "aurum-tinyseed-install-plan-v1",
        "boot_disk": _boot_disk(),
        "targets": targets,
        "available": bool(targets),
        "warning": "The selected target disk will be completely erased; the boot medium is excluded.",
    }


def _wait_partitions(paths: list[Path]) -> None:
    for _ in range(30):
        if all(path.exists() for path in paths):
            return
        time.sleep(0.25)
    raise InstallError("new partitions did not appear")


def _copy_root(target_root: Path, *, exclude_boot_firmware: bool = False) -> None:
    excludes = [
        "/dev/***", "/proc/***", "/sys/***", "/run/***", "/tmp/***", "/mnt/***", "/media/***",
        "/lost+found", "/var/lib/aurum/germ/build/***",
    ]
    if exclude_boot_firmware:
        excludes.append("/boot/firmware/***")
    args = ["rsync", "-aHAX", "--numeric-ids", "--one-file-system"]
    for item in excludes:
        args.append(f"--exclude={item}")
    args.extend(["/", f"{target_root}/"])
    _run(args, timeout=1800)
    for rel in ("dev", "proc", "sys", "run", "tmp", "mnt", "media"):
        (target_root / rel).mkdir(parents=True, exist_ok=True)
    os.chmod(target_root / "tmp", 0o1777)


def _uuid(device: Path) -> str:
    value = _run(["blkid", "-s", "UUID", "-o", "value", str(device)], timeout=20).stdout.strip()
    if not re.fullmatch(r"[A-Fa-f0-9-]{8,64}", value):
        raise InstallError(f"invalid filesystem UUID for {device}")
    return value


def _kernel_pair(root: Path) -> tuple[str, str]:
    kernels = sorted((root / "boot").glob("vmlinuz-*"), reverse=True)
    for kernel in kernels:
        version = kernel.name.removeprefix("vmlinuz-")
        initrd = root / "boot" / f"initrd.img-{version}"
        if initrd.is_file():
            return kernel.name, initrd.name
    raise InstallError("installed Tiny Seed has no matching kernel/initramfs")


def _write_common(root: Path, *, root_uuid: str, boot_line: str) -> None:
    (root / "etc").mkdir(parents=True, exist_ok=True)
    machine_id = root / "etc/machine-id"
    machine_id.write_text("", encoding="utf-8")
    (root / "etc/aurum-tinyseed-installed.json").write_text(
        json.dumps(
            {
                "schema": "aurum-tinyseed-installed-v1",
                "installed_at_unix": int(time.time()),
                "root_uuid": root_uuid,
                "boot": boot_line,
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )


def _chroot_regrow(root: Path) -> dict[str, Any]:
    mounted: list[Path] = []
    try:
        for source, rel, mode in (("/dev", "dev", "bind"), ("/run", "run", "bind")):
            target = root / rel
            target.mkdir(parents=True, exist_ok=True)
            _run(["mount", "--bind", source, str(target)], timeout=20)
            mounted.append(target)
        for fs, rel in (("proc", "proc"), ("sysfs", "sys")):
            target = root / rel
            target.mkdir(parents=True, exist_ok=True)
            _run(["mount", "-t", fs, fs, str(target)], timeout=20)
            mounted.append(target)
        result = _run(
            [
                "chroot",
                str(root),
                "/usr/bin/python3",
                "/usr/lib/aurum/germ/reseed.py",
                "regrow",
                "--ref",
                "main",
                "--authorize-network",
            ],
            timeout=1200,
        )
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"status": "finished", "detail": result.stdout.strip()[-2000:]}
    finally:
        for target in reversed(mounted):
            _run(["umount", "-l", str(target)], timeout=20, check=False)


def _install_x86(target: dict[str, Any], *, regrow_current: bool) -> dict[str, Any]:
    device = target["device"]
    p1, p2, p3 = (_partition(device, n) for n in (1, 2, 3))
    _run(["wipefs", "--all", "--force", device])
    _run(
        [
            "parted", "--script", "--align", "optimal", device,
            "mklabel", "gpt",
            "mkpart", "AURUM_BIOS", "1MiB", "3MiB", "set", "1", "bios_grub", "on",
            "mkpart", "AURUM_EFI", "fat32", "3MiB", "515MiB", "set", "2", "esp", "on",
            "mkpart", "AURUM_ROOT", "ext4", "515MiB", "100%",
        ]
    )
    _run(["partprobe", device], check=False)
    _run(["udevadm", "settle"], check=False)
    _wait_partitions([p1, p2, p3])
    _run(["mkfs.vfat", "-F", "32", "-n", "AURUM_EFI", str(p2)])
    _run(["mkfs.ext4", "-F", "-L", "AURUM_ROOT", str(p3)])

    with tempfile.TemporaryDirectory(prefix="aurum-install-") as td:
        root = Path(td) / "root"
        root.mkdir()
        efi = root / "boot/efi"
        efi.mkdir(parents=True)
        _run(["mount", str(p3), str(root)])
        efi_mounted = False
        try:
            _copy_root(root)
            efi.mkdir(parents=True, exist_ok=True)
            _run(["mount", str(p2), str(efi)])
            efi_mounted = True
            root_uuid = _uuid(p3)
            efi_uuid = _uuid(p2)
            (root / "etc/fstab").write_text(
                f"UUID={root_uuid} / ext4 defaults,noatime 0 1\nUUID={efi_uuid} /boot/efi vfat umask=0077 0 2\n",
                encoding="utf-8",
            )
            _write_common(root, root_uuid=root_uuid, boot_line="x86-dual-uefi-bios")
            _run([
                "grub-install", "--target=x86_64-efi", f"--efi-directory={efi}",
                f"--boot-directory={root / 'boot'}", "--removable", "--no-nvram", "--recheck",
            ], timeout=120)
            if shutil.which("grub-install"):
                _run([
                    "grub-install", "--target=i386-pc", f"--boot-directory={root / 'boot'}", "--recheck", device,
                ], timeout=120, check=False)
            kernel, initrd = _kernel_pair(root)
            grub = root / "boot/grub/grub.cfg"
            grub.parent.mkdir(parents=True, exist_ok=True)
            grub.write_text(
                "set default=0\nset timeout=1\n"
                "menuentry 'Aurum Tiny Seed / current phenotype' {\n"
                f" search --no-floppy --fs-uuid --set=root {root_uuid}\n"
                f" linux /boot/{kernel} root=UUID={root_uuid} ro quiet\n"
                f" initrd /boot/{initrd}\n"
                "}\n",
                encoding="utf-8",
            )
            regrow = _chroot_regrow(root) if regrow_current else {"status": "deferred"}
            _run(["sync"], check=False)
        finally:
            if efi_mounted:
                _run(["umount", str(efi)], check=False)
            _run(["umount", str(root)], check=False)
    _run(["blockdev", "--flushbufs", device], check=False)
    return {
        "status": "installed",
        "device": device,
        "root_device": str(p3),
        "platform": "x86_64",
        "regrow": regrow,
    }


def _install_pi(target: dict[str, Any], *, regrow_current: bool) -> dict[str, Any]:
    device = target["device"]
    p1, p2 = (_partition(device, n) for n in (1, 2))
    source_boot = Path("/boot/firmware")
    if not source_boot.is_dir() or not (source_boot / "config.txt").exists():
        raise InstallError("running Tiny Seed does not expose a Raspberry Pi firmware boot tree")
    _run(["wipefs", "--all", "--force", device])
    _run([
        "parted", "--script", "--align", "optimal", device,
        "mklabel", "msdos",
        "mkpart", "primary", "fat32", "1MiB", "513MiB", "set", "1", "boot", "on",
        "mkpart", "primary", "ext4", "513MiB", "100%",
    ])
    _run(["partprobe", device], check=False)
    _run(["udevadm", "settle"], check=False)
    _wait_partitions([p1, p2])
    _run(["mkfs.vfat", "-F", "32", "-n", "AURUM_BOOT", str(p1)])
    _run(["mkfs.ext4", "-F", "-L", "AURUM_ROOT", str(p2)])

    with tempfile.TemporaryDirectory(prefix="aurum-pi-install-") as td:
        root = Path(td) / "root"
        boot = root / "boot/firmware"
        root.mkdir()
        _run(["mount", str(p2), str(root)])
        boot_mounted = False
        try:
            _copy_root(root, exclude_boot_firmware=True)
            boot.mkdir(parents=True, exist_ok=True)
            _run(["mount", str(p1), str(boot)])
            boot_mounted = True
            _run(["rsync", "-aH", f"{source_boot}/", f"{boot}/"], timeout=300)
            root_uuid = _uuid(p2)
            boot_uuid = _uuid(p1)
            (root / "etc/fstab").write_text(
                f"UUID={root_uuid} / ext4 defaults,noatime 0 1\nUUID={boot_uuid} /boot/firmware vfat defaults 0 2\n",
                encoding="utf-8",
            )
            cmdline = boot / "cmdline.txt"
            if cmdline.is_file():
                text = " ".join(cmdline.read_text(encoding="utf-8").split())
                if re.search(r"\broot=\S+", text):
                    text = re.sub(r"\broot=\S+", f"root=UUID={root_uuid}", text)
                else:
                    text += f" root=UUID={root_uuid}"
                cmdline.write_text(text + "\n", encoding="utf-8")
            _write_common(root, root_uuid=root_uuid, boot_line="raspberry-pi-firmware")
            regrow = _chroot_regrow(root) if regrow_current else {"status": "deferred"}
            _run(["sync"], check=False)
        finally:
            if boot_mounted:
                _run(["umount", str(boot)], check=False)
            _run(["umount", str(root)], check=False)
    _run(["blockdev", "--flushbufs", device], check=False)
    return {
        "status": "installed",
        "device": device,
        "root_device": str(p2),
        "platform": "arm64-pi",
        "regrow": regrow,
    }


def install(confirmation_code: str, *, architecture: str, model: str | None, regrow_current: bool = True) -> dict[str, Any]:
    if os.geteuid() != 0:
        raise InstallError("Tiny Seed install requires root")
    matches = [t for t in discover_targets() if t["confirmation_code"] == confirmation_code]
    if len(matches) != 1:
        raise InstallError("confirmation no longer identifies exactly one eligible target disk")
    target = matches[0]
    if architecture == "x86_64":
        return _install_x86(target, regrow_current=regrow_current)
    if architecture == "arm64" and model and "raspberry pi" in model.lower():
        return _install_pi(target, regrow_current=regrow_current)
    raise InstallError(f"no fresh-install adapter is proven for architecture={architecture} model={model!r}")


__all__ = ["InstallError", "discover_targets", "install", "plan"]
