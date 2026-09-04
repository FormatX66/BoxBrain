#!/usr/bin/env python3
"""Guarded whole-disk UEFI installer for the Aurum PC live image.

The public interface never accepts a device path.  A live discovery pass emits
a short confirmation code bound to one current internal disk identity, and the
install pass resolves that code against a fresh discovery before any write.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time
from typing import Any, Callable, Iterator, Mapping, Sequence

try:
    import fcntl
except ImportError:  # pragma: no cover - the installer executes only in Linux
    fcntl = None  # type: ignore[assignment]


INSTALLER_SCHEMA = "aurum-pc-guided-installer-v1"
HOPPER_TARGET_SERIAL = "BTTE934116YM512B-1"
HOPPER_TARGET_SIZE_BYTES = 512110190592
MINIMUM_TARGET_BYTES = 8 * 1024 * 1024 * 1024
LIVE_MEDIUM = Path("/run/live/medium")
EFI_RUNTIME = Path("/sys/firmware/efi")
SYS_BLOCK = Path("/sys/class/block")
INSTALL_LOCK = Path("/run/aurum-install.lock")
INSTALL_WORK = Path("/run/aurum-install")
SAFE_DEVICE = re.compile(r"/dev/(?:nvme\d+n\d+|sd[a-z]+|vd[a-z]+)")
SAFE_BOOT_FILE = re.compile(r"[A-Za-z0-9._+-]+")
SAFE_EXISTING_MOUNT_ROOTS = ("/media", "/mnt", "/run/media")
ProgressCallback = Callable[[Mapping[str, Any]], None]
Runner = Callable[..., subprocess.CompletedProcess[str]]


class InstallError(RuntimeError):
    """Raised before an unsafe or incomplete installation can continue."""


@dataclass(frozen=True)
class InstallTarget:
    device: str
    kernel_name: str
    model: str
    serial: str
    transport: str
    size_bytes: int
    size_gib: float
    existing_partitions: tuple[Mapping[str, Any], ...]
    confirmation_code: str


def _default_runner(arguments: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(arguments), **kwargs)


def _clean_text(value: object, *, maximum: int = 128) -> str:
    text = " ".join(str(value or "").split())
    return text[:maximum]


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def _mountpoints(record: Mapping[str, Any]) -> tuple[str, ...]:
    raw = record.get("mountpoints")
    if isinstance(raw, str):
        return (raw,) if raw else ()
    if isinstance(raw, list):
        return tuple(str(value) for value in raw if value)
    mountpoint = record.get("mountpoint")
    return (str(mountpoint),) if mountpoint else ()


def _all_mountpoints(record: Mapping[str, Any]) -> tuple[str, ...]:
    found = list(_mountpoints(record))
    for child in record.get("children") or ():
        if isinstance(child, Mapping):
            found.extend(_all_mountpoints(child))
    return tuple(found)


def _safe_existing_mountpoint(value: str) -> bool:
    """Allow only ordinary live-session automount locations or active swap."""
    mountpoint = str(value or "").rstrip("/") or "/"
    if mountpoint == "[SWAP]":
        return True
    return any(
        mountpoint == root or mountpoint.startswith(root + "/")
        for root in SAFE_EXISTING_MOUNT_ROOTS
    )


def _confirmation_code(*, device: str, serial: str, size_bytes: int) -> str:
    identity = json.dumps(
        {"device": device, "serial": serial, "size_bytes": size_bytes},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "ERASE-" + hashlib.sha256(identity).hexdigest()[:8].upper()


class AurumInstaller:
    def __init__(
        self,
        *,
        runner: Runner = _default_runner,
        live_medium: Path = LIVE_MEDIUM,
        efi_runtime: Path = EFI_RUNTIME,
        sys_block: Path = SYS_BLOCK,
        install_lock: Path = INSTALL_LOCK,
        install_work: Path = INSTALL_WORK,
    ) -> None:
        self.runner = runner
        self.live_medium = live_medium
        self.efi_runtime = efi_runtime
        self.sys_block = sys_block
        self.install_lock = install_lock
        self.install_work = install_work

    def _invoke(self, arguments: Sequence[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        try:
            result = self.runner(
                list(arguments),
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            raise InstallError(
                f"{Path(arguments[0]).name} is unavailable: {exc.strerror or type(exc).__name__}"
            ) from exc
        if check and result.returncode != 0:
            detail = _clean_text(result.stderr or result.stdout or "command failed", maximum=300)
            raise InstallError(f"{Path(arguments[0]).name} failed: {detail}")
        return result

    def _block_tree(self) -> list[Mapping[str, Any]]:
        result = self._invoke(
            [
                "lsblk",
                "--json",
                "--bytes",
                "--paths",
                "--output",
                "NAME,KNAME,PATH,TYPE,SIZE,MODEL,SERIAL,TRAN,RM,RO,HOTPLUG,FSTYPE,LABEL,MOUNTPOINTS",
            ]
        )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise InstallError("disk inventory was not valid JSON") from exc
        devices = payload.get("blockdevices") if isinstance(payload, Mapping) else None
        if not isinstance(devices, list):
            raise InstallError("disk inventory did not contain block devices")
        return [record for record in devices if isinstance(record, Mapping)]

    def _eligible(self, record: Mapping[str, Any]) -> bool:
        device = str(record.get("path") or record.get("name") or "")
        transport = str(record.get("tran") or "").lower()
        size = int(record.get("size") or 0)
        kernel_name = Path(str(record.get("kname") or device)).name
        if record.get("type") != "disk" or not SAFE_DEVICE.fullmatch(device):
            return False
        if size < MINIMUM_TARGET_BYTES or _truthy(record.get("ro")):
            return False
        if _truthy(record.get("rm")) or _truthy(record.get("hotplug")) or transport == "usb":
            return False
        if device.startswith("/dev/vd"):
            if transport not in {"", "virtio"}:
                return False
        elif transport not in {"ata", "nvme", "sata", "sas", "scsi"}:
            return False
        if kernel_name.startswith(("loop", "sr", "dm-")):
            return False
        return all(_safe_existing_mountpoint(value) for value in _all_mountpoints(record))

    def discover_targets(self) -> tuple[InstallTarget, ...]:
        targets: list[InstallTarget] = []
        for record in self._block_tree():
            if not self._eligible(record):
                continue
            device = str(record.get("path") or record.get("name"))
            kernel_name = Path(str(record.get("kname") or device)).name
            size_bytes = int(record.get("size") or 0)
            serial = _clean_text(record.get("serial")) or "serial-unavailable"
            partitions: list[Mapping[str, Any]] = []
            for child in record.get("children") or ():
                if not isinstance(child, Mapping) or child.get("type") != "part":
                    continue
                partitions.append(
                    {
                        "device": str(child.get("path") or child.get("name") or ""),
                        "size_bytes": int(child.get("size") or 0),
                        "filesystem": _clean_text(child.get("fstype")),
                        "label": _clean_text(child.get("label")),
                        "mountpoints": _mountpoints(child),
                    }
                )
            targets.append(
                InstallTarget(
                    device=device,
                    kernel_name=kernel_name,
                    model=_clean_text(record.get("model")) or "unknown-model",
                    serial=serial,
                    transport=_clean_text(record.get("tran")) or "virtio",
                    size_bytes=size_bytes,
                    size_gib=round(size_bytes / (1024**3), 1),
                    existing_partitions=tuple(partitions),
                    confirmation_code=_confirmation_code(
                        device=device,
                        serial=serial,
                        size_bytes=size_bytes,
                    ),
                )
            )
        return tuple(sorted(targets, key=lambda item: item.device))

    def plan(self) -> dict[str, Any]:
        if not self.live_medium.is_dir():
            return {
                "schema": INSTALLER_SCHEMA,
                "available": False,
                "reason": "installer-runs-only-from-aurum-live-media",
                "targets": [],
            }
        targets = self.discover_targets()
        return {
            "schema": INSTALLER_SCHEMA,
            "available": bool(targets),
            "reason": "ready" if targets else "no-unmounted-internal-disk-found",
            "mode": "guided-whole-disk-dual-boot",
            "live_boot_mode": "uefi" if self.efi_runtime.is_dir() else "legacy",
            "warning": "The selected disk will be completely erased. Other disks are never modified.",
            "targets": [
                {
                    **asdict(target),
                    "repair_available": self._repair_available(target),
                    "confirm_command": f"install confirm {target.confirmation_code}",
                }
                for target in targets
            ],
        }

    @contextmanager
    def _exclusive_install(self) -> Iterator[None]:
        if fcntl is None:
            raise InstallError("the Aurum installer requires its Linux live runtime")
        self.install_lock.parent.mkdir(parents=True, exist_ok=True)
        with self.install_lock.open("a+", encoding="utf-8") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise InstallError("an Aurum installation is already running") from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _assert_live_safety(self, target: InstallTarget) -> None:
        if os.geteuid() != 0:
            raise InstallError("installation requires the root-owned Aurum live console")
        if not self.live_medium.is_dir():
            raise InstallError("installation is allowed only while booted from Aurum live media")
        device = Path(target.device)
        try:
            mode = device.stat().st_mode
        except OSError as exc:
            raise InstallError("selected disk disappeared before installation") from exc
        if not stat.S_ISBLK(mode):
            raise InstallError("selected target is no longer a block device")
        sys_device = self.sys_block / target.kernel_name
        try:
            resolved = str(sys_device.resolve(strict=True)).lower()
        except OSError as exc:
            raise InstallError("selected disk has no stable kernel identity") from exc
        if "/usb" in resolved.replace("\\", "/"):
            raise InstallError("USB disks cannot be internal installation targets")

    @staticmethod
    def _partition_paths(device: str) -> tuple[Path, Path, Path]:
        suffix = "p" if device[-1:].isdigit() else ""
        return (
            Path(f"{device}{suffix}1"),
            Path(f"{device}{suffix}2"),
            Path(f"{device}{suffix}3"),
        )

    def _release_existing_mounts(self, target: InstallTarget) -> None:
        mounts: set[str] = set()
        swaps: set[str] = set()
        for partition in target.existing_partitions:
            device = str(partition.get("device") or "")
            mountpoints = tuple(str(value) for value in partition.get("mountpoints") or () if value)
            for mountpoint in mountpoints:
                if not _safe_existing_mountpoint(mountpoint):
                    raise InstallError("the selected disk gained a protected mount before installation")
                if mountpoint == "[SWAP]":
                    if device:
                        swaps.add(device)
                else:
                    mounts.add(mountpoint)
        for device in sorted(swaps):
            self._invoke(["swapoff", device])
        for mountpoint in sorted(mounts, key=lambda value: (value.count("/"), len(value)), reverse=True):
            self._invoke(["umount", mountpoint])
        if mounts or swaps:
            self._invoke(["udevadm", "settle"])

    @staticmethod
    def _kernel_pair(root: Path) -> tuple[str, str]:
        for kernel in sorted((root / "boot").glob("vmlinuz-*"), reverse=True):
            version = kernel.name.removeprefix("vmlinuz-")
            initrd = root / "boot" / f"initrd.img-{version}"
            if initrd.is_file() and SAFE_BOOT_FILE.fullmatch(kernel.name) and SAFE_BOOT_FILE.fullmatch(initrd.name):
                return kernel.name, initrd.name
        raise InstallError("installed filesystem has no matching kernel and initramfs")

    def _uuid(self, device: Path) -> str:
        result = self._invoke(["blkid", "-s", "UUID", "-o", "value", str(device)])
        value = result.stdout.strip()
        if not re.fullmatch(r"[A-Fa-f0-9-]{8,64}", value):
            raise InstallError(f"filesystem UUID is invalid for {device}")
        return value

    @staticmethod
    def _repair_partitions(target: InstallTarget) -> tuple[Path, Path]:
        efi: list[Path] = []
        root: list[Path] = []
        for partition in target.existing_partitions:
            device = str(partition.get("device") or "")
            label = str(partition.get("label") or "").upper()
            filesystem = str(partition.get("filesystem") or "").lower()
            if not device.startswith(target.device):
                continue
            if label == "AURUM_EFI" and filesystem in {"vfat", "fat", "fat32"}:
                efi.append(Path(device))
            elif label == "AURUM_ROOT" and filesystem == "ext4":
                root.append(Path(device))
        if len(efi) != 1 or len(root) != 1:
            raise InstallError("the selected drive does not contain one repairable Aurum installation")
        return efi[0], root[0]

    def _repair_available(self, target: InstallTarget) -> bool:
        try:
            self._repair_partitions(target)
        except InstallError:
            return False
        return True

    @staticmethod
    def _is_hopper_target(target: InstallTarget) -> bool:
        return (
            target.serial == HOPPER_TARGET_SERIAL
            and target.size_bytes == HOPPER_TARGET_SIZE_BYTES
        )

    @staticmethod
    def _write_machine_identity(target_root: Path, target: InstallTarget, receipt: Mapping[str, Any]) -> None:
        is_hopper = AurumInstaller._is_hopper_target(target)
        policy_path = target_root / "opt" / "aurum" / "pc01_autonomy_policy.json"
        try:
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            policy = {}
        if not isinstance(policy, dict):
            policy = {}
        policy.update(
            {
                "schema": "aurum-pc-autonomy-policy-v1",
                "enabled": True,
                "machine_display_name": "Hopper" if is_hopper else "Aurum PC",
                "hostname": "hopper" if is_hopper else "aurum-pc",
                "machine_match": {
                    "installed_target_serial": target.serial,
                    "installed_target_size_bytes": target.size_bytes,
                },
            }
        )
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        policy_path.write_text(json.dumps(policy, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (target_root / "etc" / "hostname").write_text(
            str(policy["hostname"]) + "\n", encoding="utf-8"
        )
        (target_root / "etc" / "aurum-installed.json").write_text(
            json.dumps(dict(receipt), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _write_boot_config(
        target_root: Path,
        root_uuid: str,
        target: InstallTarget,
    ) -> tuple[str, str]:
        kernel_name, initrd_name = AurumInstaller._kernel_pair(target_root)
        grub_dir = target_root / "boot" / "grub"
        grub_dir.mkdir(parents=True, exist_ok=True)
        common_arguments = (
            f"root=UUID={root_uuid} ro quiet preempt=voluntary "
            "transparent_hugepage=madvise console=tty0 console=ttyS0,115200n8"
        )
        normal_arguments = common_arguments
        if AurumInstaller._is_hopper_target(target):
            # Hopper's discrete NVIDIA path has physically stalled in nouveau
            # timer handling. Keep other native graphics available while
            # excluding only that failed driver from the normal boot.
            normal_arguments += " modprobe.blacklist=nouveau nouveau.modeset=0"
        recovery_arguments = common_arguments + " nomodeset"
        (grub_dir / "grub.cfg").write_text(
            "set default=0\n"
            "set timeout=5\n\n"
            f"search --no-floppy --fs-uuid --set=aurum_root {root_uuid}\n"
            "menuentry 'Aurum PC' {\n"
            f"    search --no-floppy --fs-uuid --set=root {root_uuid}\n"
            f"    linux /boot/{kernel_name} {normal_arguments}\n"
            f"    initrd /boot/{initrd_name}\n"
            "}\n"
            "menuentry 'Aurum PC (graphics recovery)' {\n"
            f"    search --no-floppy --fs-uuid --set=root {root_uuid}\n"
            f"    linux /boot/{kernel_name} {recovery_arguments}\n"
            f"    initrd /boot/{initrd_name}\n"
            "}\n",
            encoding="utf-8",
        )
        return kernel_name, initrd_name

    @staticmethod
    def _refresh_runtime_assets(target_root: Path) -> None:
        """Refresh repair-safe runtime assets while preserving user and machine state."""
        source_systemd = Path("/etc/systemd/system")
        target_systemd = target_root / "etc" / "systemd" / "system"
        target_systemd.mkdir(parents=True, exist_ok=True)
        essential = {
            "aurum-auto-sync.service",
            "aurum-core-share.service",
            "aurum-input-bootstrap.service",
            "aurum-network-bootstrap.service",
            "aurum-pc-console.service",
            "aurum-setup.service",
        }
        for name in essential:
            source = source_systemd / name
            if source.is_file():
                shutil.copy2(source, target_systemd / name)
        wants = target_systemd / "multi-user.target.wants"
        wants.mkdir(parents=True, exist_ok=True)
        for name in essential:
            service = target_systemd / name
            if not service.is_file():
                continue
            link = wants / name
            if link.exists() or link.is_symlink():
                link.unlink()
            link.symlink_to(Path("..") / name)

        live_wifi = Path("/var/lib/aurum/state/wifi.conf")
        if live_wifi.is_file():
            installed_wifi = target_root / "var" / "lib" / "aurum" / "state" / "wifi.conf"
            installed_wifi.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(live_wifi, installed_wifi)
            os.chmod(installed_wifi, 0o600)

    def _progress(self, callback: ProgressCallback | None, phase: str, **details: Any) -> None:
        if callback is not None:
            callback({"phase": phase, **details})

    def _execute(self, target: InstallTarget, callback: ProgressCallback | None) -> dict[str, Any]:
        self._assert_live_safety(target)
        bios_partition, efi_partition, root_partition = self._partition_paths(target.device)
        self._progress(callback, "unmount", device=target.device)
        self._release_existing_mounts(target)
        self._progress(callback, "partition", device=target.device)
        self._invoke(["wipefs", "--all", "--force", target.device])
        self._invoke(
            [
                "parted",
                "--script",
                "--align",
                "optimal",
                target.device,
                "mklabel",
                "gpt",
                "mkpart",
                "AURUM_BIOS",
                "1MiB",
                "3MiB",
                "set",
                "1",
                "bios_grub",
                "on",
                "mkpart",
                "AURUM_EFI",
                "fat32",
                "3MiB",
                "515MiB",
                "set",
                "2",
                "esp",
                "on",
                "mkpart",
                "AURUM_ROOT",
                "ext4",
                "515MiB",
                "100%",
            ]
        )
        self._invoke(["partprobe", target.device])
        self._invoke(["udevadm", "settle"])
        for _ in range(20):
            if bios_partition.exists() and efi_partition.exists() and root_partition.exists():
                break
            time.sleep(0.25)
        else:
            raise InstallError("new Aurum partitions did not appear")

        self._progress(callback, "format", device=target.device)
        self._invoke(["mkfs.vfat", "-F", "32", "-n", "AURUM_EFI", str(efi_partition)])
        self._invoke(["mkfs.ext4", "-F", "-L", "AURUM_ROOT", str(root_partition)])

        target_root = self.install_work / "root"
        if target_root.exists() and any(target_root.iterdir()):
            raise InstallError("installer workspace is unexpectedly non-empty")
        target_root.mkdir(parents=True, mode=0o700, exist_ok=True)
        root_mounted = False
        efi_mounted = False
        try:
            self._invoke(["mount", str(root_partition), str(target_root)])
            root_mounted = True
            self._progress(callback, "copy", device=target.device)
            self._invoke(
                [
                    "rsync",
                    "-aHAX",
                    "--numeric-ids",
                    "--one-file-system",
                    "--exclude=/dev/***",
                    "--exclude=/proc/***",
                    "--exclude=/sys/***",
                    "--exclude=/run/***",
                    "--exclude=/tmp/***",
                    "--exclude=/mnt/***",
                    "--exclude=/media/***",
                    "/",
                    f"{target_root}/",
                ]
            )
            for relative in ("dev", "proc", "sys", "run", "tmp", "mnt", "media", "boot/efi"):
                path = target_root / relative
                path.mkdir(parents=True, exist_ok=True)
            os.chmod(target_root / "tmp", 0o1777)
            self._invoke(["mount", str(efi_partition), str(target_root / "boot" / "efi")])
            efi_mounted = True

            root_uuid = self._uuid(root_partition)
            efi_uuid = self._uuid(efi_partition)
            (target_root / "etc" / "fstab").write_text(
                "# Aurum guided installer v1\n"
                f"UUID={root_uuid} / ext4 defaults,noatime 0 1\n"
                f"UUID={efi_uuid} /boot/efi vfat umask=0077 0 2\n",
                encoding="utf-8",
            )
            machine_id = target_root / "etc" / "machine-id"
            if machine_id.exists() or machine_id.is_symlink():
                machine_id.unlink()
            machine_id.write_text("", encoding="utf-8")
            receipt = {
                "schema": INSTALLER_SCHEMA,
                "mode": "installed",
                "installed_at": datetime.now(timezone.utc).isoformat(),
                "target": {
                    "model": target.model,
                    "serial": target.serial,
                    "size_bytes": target.size_bytes,
                },
                "root_uuid": root_uuid,
                "efi_uuid": efi_uuid,
            }
            self._write_machine_identity(target_root, target, receipt)

            self._progress(callback, "bootloader", device=target.device)
            self._invoke(
                [
                    "grub-install",
                    "--target=x86_64-efi",
                    f"--efi-directory={target_root / 'boot' / 'efi'}",
                    f"--boot-directory={target_root / 'boot'}",
                    "--removable",
                    "--no-nvram",
                    "--recheck",
                ]
            )
            self._invoke(
                [
                    "grub-install",
                    "--target=i386-pc",
                    f"--boot-directory={target_root / 'boot'}",
                    "--recheck",
                    target.device,
                ]
            )
            kernel_name, initrd_name = self._write_boot_config(target_root, root_uuid, target)

            self._progress(callback, "verify", device=target.device)
            required = (
                target_root / "boot" / "efi" / "EFI" / "BOOT" / "BOOTX64.EFI",
                target_root / "boot" / "grub" / "i386-pc" / "core.img",
                target_root / "boot" / kernel_name,
                target_root / "boot" / initrd_name,
                target_root / "boot" / "grub" / "grub.cfg",
                target_root / "etc" / "fstab",
                target_root / "etc" / "aurum-installed.json",
                target_root / "opt" / "aurum" / "aurum_console.py",
            )
            missing = [str(path.relative_to(target_root)) for path in required if not path.is_file()]
            if missing:
                raise InstallError("installed verification files are missing: " + ",".join(missing))
            self._invoke(["sync"])
            self._invoke(["umount", str(target_root / "boot" / "efi")])
            efi_mounted = False
            self._invoke(["umount", str(target_root)])
            root_mounted = False
        finally:
            if efi_mounted:
                self._invoke(["umount", str(target_root / "boot" / "efi")], check=False)
            if root_mounted:
                self._invoke(["umount", str(target_root)], check=False)
            try:
                target_root.rmdir()
                self.install_work.rmdir()
            except OSError:
                pass

        self._invoke(["blockdev", "--flushbufs", target.device])
        self._progress(callback, "complete", device=target.device)
        return {
            "schema": INSTALLER_SCHEMA,
            "status": "installed",
            "device": target.device,
            "model": target.model,
            "size_gib": target.size_gib,
            "boot_mode": "uefi-and-legacy-fallback",
            "other_disks_modified": False,
            "next_action": "poweroff, remove the USB drive, then start the PC",
        }

    def _execute_repair(self, target: InstallTarget, callback: ProgressCallback | None) -> dict[str, Any]:
        """Repair an existing Aurum filesystem and both boot paths without erasing it."""
        self._assert_live_safety(target)
        efi_partition, root_partition = self._repair_partitions(target)
        self._progress(callback, "unmount", device=target.device)
        self._release_existing_mounts(target)

        self._progress(callback, "filesystem", device=target.device)
        checked = self._invoke(["e2fsck", "-p", str(root_partition)], check=False)
        if checked.returncode not in {0, 1}:
            detail = _clean_text(checked.stderr or checked.stdout or "filesystem check failed", maximum=300)
            raise InstallError(f"e2fsck could not safely repair the Aurum filesystem: {detail}")

        target_root = self.install_work / "repair-root"
        if target_root.exists() and any(target_root.iterdir()):
            raise InstallError("repair workspace is unexpectedly non-empty")
        target_root.mkdir(parents=True, mode=0o700, exist_ok=True)
        root_mounted = False
        efi_mounted = False
        try:
            self._invoke(["mount", str(root_partition), str(target_root)])
            root_mounted = True
            if not (target_root / "opt" / "aurum").is_dir():
                raise InstallError("the selected drive is labeled Aurum but its runtime is missing")

            self._progress(callback, "copy", device=target.device)
            self._invoke(
                [
                    "rsync",
                    "-aHAX",
                    "--delete",
                    "/opt/aurum/",
                    f"{target_root / 'opt' / 'aurum'}/",
                ]
            )
            self._refresh_runtime_assets(target_root)
            (target_root / "boot" / "efi").mkdir(parents=True, exist_ok=True)
            self._invoke(["mount", str(efi_partition), str(target_root / "boot" / "efi")])
            efi_mounted = True

            root_uuid = self._uuid(root_partition)
            efi_uuid = self._uuid(efi_partition)
            receipt_path = target_root / "etc" / "aurum-installed.json"
            try:
                old_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                old_receipt = {}
            receipt = dict(old_receipt) if isinstance(old_receipt, dict) else {}
            receipt.update(
                {
                    "schema": INSTALLER_SCHEMA,
                    "mode": "installed",
                    "repaired_at": datetime.now(timezone.utc).isoformat(),
                    "target": {
                        "model": target.model,
                        "serial": target.serial,
                        "size_bytes": target.size_bytes,
                    },
                    "root_uuid": root_uuid,
                    "efi_uuid": efi_uuid,
                }
            )
            self._write_machine_identity(target_root, target, receipt)
            (target_root / "etc" / "fstab").write_text(
                "# Aurum guided installer v1\n"
                f"UUID={root_uuid} / ext4 defaults,noatime 0 1\n"
                f"UUID={efi_uuid} /boot/efi vfat umask=0077 0 2\n",
                encoding="utf-8",
            )

            self._progress(callback, "bootloader", device=target.device)
            self._invoke(
                [
                    "grub-install",
                    "--target=x86_64-efi",
                    f"--efi-directory={target_root / 'boot' / 'efi'}",
                    f"--boot-directory={target_root / 'boot'}",
                    "--removable",
                    "--no-nvram",
                    "--recheck",
                ]
            )
            self._invoke(
                [
                    "grub-install",
                    "--target=i386-pc",
                    f"--boot-directory={target_root / 'boot'}",
                    "--recheck",
                    target.device,
                ]
            )
            kernel_name, initrd_name = self._write_boot_config(target_root, root_uuid, target)

            self._progress(callback, "verify", device=target.device)
            required = (
                target_root / "boot" / "efi" / "EFI" / "BOOT" / "BOOTX64.EFI",
                target_root / "boot" / "grub" / "i386-pc" / "core.img",
                target_root / "boot" / kernel_name,
                target_root / "boot" / initrd_name,
                target_root / "boot" / "grub" / "grub.cfg",
                target_root / "etc" / "aurum-installed.json",
                target_root / "opt" / "aurum" / "aurum_console.py",
            )
            missing = [str(path.relative_to(target_root)) for path in required if not path.is_file()]
            if missing:
                raise InstallError("repair verification files are missing: " + ",".join(missing))
            self._invoke(["sync"])
            self._invoke(["umount", str(target_root / "boot" / "efi")])
            efi_mounted = False
            self._invoke(["umount", str(target_root)])
            root_mounted = False
        finally:
            if efi_mounted:
                self._invoke(["umount", str(target_root / "boot" / "efi")], check=False)
            if root_mounted:
                self._invoke(["umount", str(target_root)], check=False)
            try:
                target_root.rmdir()
                self.install_work.rmdir()
            except OSError:
                pass

        self._invoke(["blockdev", "--flushbufs", target.device])
        self._progress(callback, "complete", device=target.device)
        return {
            "schema": INSTALLER_SCHEMA,
            "status": "repaired",
            "device": target.device,
            "model": target.model,
            "size_gib": target.size_gib,
            "boot_mode": "uefi-and-legacy-fallback",
            "other_disks_modified": False,
            "next_action": "poweroff, remove the USB drive, then start the PC",
        }

    def install(self, confirmation_code: str, *, progress: ProgressCallback | None = None) -> dict[str, Any]:
        if not re.fullmatch(r"ERASE-[A-F0-9]{8}", confirmation_code):
            raise InstallError("confirmation must exactly match one current ERASE code from the install plan")
        with self._exclusive_install():
            self._progress(progress, "preflight")
            matches = [
                target
                for target in self.discover_targets()
                if target.confirmation_code == confirmation_code
            ]
            if len(matches) != 1:
                raise InstallError("confirmation no longer identifies exactly one eligible internal disk")
            return self._execute(matches[0], progress)

    def repair(self, confirmation_code: str, *, progress: ProgressCallback | None = None) -> dict[str, Any]:
        if not re.fullmatch(r"ERASE-[A-F0-9]{8}", confirmation_code):
            raise InstallError("repair selection no longer identifies one current internal drive")
        with self._exclusive_install():
            self._progress(progress, "preflight")
            matches = [
                target
                for target in self.discover_targets()
                if target.confirmation_code == confirmation_code and self._repair_available(target)
            ]
            if len(matches) != 1:
                raise InstallError("repair selection no longer identifies one repairable Aurum drive")
            return self._execute_repair(matches[0], progress)


__all__ = [
    "AurumInstaller",
    "INSTALLER_SCHEMA",
    "InstallError",
    "InstallTarget",
    "MINIMUM_TARGET_BYTES",
]
