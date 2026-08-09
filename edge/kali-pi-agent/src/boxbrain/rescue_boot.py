"""Guarded one-shot rescue-media state and image registry.

The pending selection is consumed at early boot and reset to ``normal`` before
the selected image is returned.  A failure later in the boot cannot therefore
leave the Pi armed for another rescue boot.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
from typing import Any, Callable, Iterable


ARM_CONFIRMATION = "ARM ONE-SHOT RESCUE"
CANCEL_CONFIRMATION = "CANCEL ONE-SHOT RESCUE"
IMPORT_CONFIRMATION = "IMPORT VERIFIED RESCUE IMAGE"
REBOOT_NORMAL_CONFIRMATION = "REBOOT NORMAL BOXBRAIN"

_IMAGE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_KINDS = {"kali", "windows", "custom"}
_ARCHITECTURES = {"arm64", "x86_64", "multi"}
_WRITE_MODES = {"read-only", "read-write"}
_BOOT_COMPATIBILITY = {"bios", "uefi", "pi4"}


class RescueBootError(RuntimeError):
    """Raised when a rescue operation is invalid or cannot be verified."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalized_architecture(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    aliases = {
        "amd64": "x86_64",
        "x64": "x86_64",
        "aarch64": "arm64",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in _ARCHITECTURES:
        raise RescueBootError(f"Unsupported rescue architecture: {value}")
    return normalized


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class RescueBootManager:
    """Manage verified rescue images and consumed next-boot state."""

    def __init__(
        self,
        state_directory: str | Path,
        *,
        system_root: str | Path = "/",
        reboot_runner: Callable[[list[str]], Any] | None = None,
    ) -> None:
        self.state_directory = Path(state_directory).resolve()
        self.rescue_directory = self.state_directory / "rescue"
        self.image_directory = self.state_directory / "rescue-images"
        self.backup_directory = self.rescue_directory / "backups"
        self.registry_path = self.rescue_directory / "images.json"
        self.next_boot_path = self.rescue_directory / "next-boot.json"
        self.active_boot_path = self.rescue_directory / "active-boot.json"
        self.history_path = self.rescue_directory / "history.jsonl"
        self.system_root = Path(system_root)
        self.reboot_runner = reboot_runner or self._run_reboot

    def initialize(self) -> None:
        self.rescue_directory.mkdir(parents=True, exist_ok=True)
        self.image_directory.mkdir(parents=True, exist_ok=True)
        self.backup_directory.mkdir(parents=True, exist_ok=True)
        if not self.registry_path.exists():
            self._write_json(
                self.registry_path,
                {"schema_version": 1, "images": []},
            )
        if not self.next_boot_path.exists():
            self._write_next_boot(self._normal_state("initialize"))

    def status(self) -> dict[str, Any]:
        self.initialize()
        pending = self._load_next_boot()
        active = self._read_json(self.active_boot_path, default=None)
        registry = self._load_registry()
        return {
            "schema_version": 1,
            "pending": pending,
            "active": active,
            "image_count": len(registry["images"]),
            "next_pi_boot": (
                "NORMAL BOXBRAIN"
                if pending["mode"] == "normal"
                else pending["mode"].upper()
            ),
            "one_shot": True,
        }

    def list_images(self, *, verify: bool = True) -> list[dict[str, Any]]:
        self.initialize()
        images: list[dict[str, Any]] = []
        for raw in self._load_registry()["images"]:
            item = dict(raw)
            try:
                path = self._validated_image_path(item)
                if verify:
                    item["checksum_valid"] = _sha256(path) == item["sha256"]
                else:
                    item["checksum_valid"] = None
                item["available"] = True
            except (OSError, RescueBootError):
                item["checksum_valid"] = False if verify else None
                item["available"] = False
            images.append(item)
        return images

    def import_image(
        self,
        source: str | Path,
        *,
        image_id: str,
        kind: str,
        architecture: str,
        boot_compatibility: Iterable[str],
        secure_boot: str,
        signed: bool | None,
        write_mode: str = "read-only",
        expected_sha256: str | None = None,
        authorization: str,
    ) -> dict[str, Any]:
        if authorization != IMPORT_CONFIRMATION:
            raise RescueBootError("Exact rescue-image import confirmation is required.")
        self.initialize()
        if not _IMAGE_ID.fullmatch(image_id):
            raise RescueBootError("Image ID must use lowercase letters, numbers, dot, dash, or underscore.")
        kind = kind.strip().lower()
        if kind not in _KINDS:
            raise RescueBootError(f"Unsupported rescue image kind: {kind}")
        architecture = _normalized_architecture(architecture)
        write_mode = write_mode.strip().lower()
        if write_mode not in _WRITE_MODES:
            raise RescueBootError(f"Unsupported write mode: {write_mode}")
        compatibility = sorted({item.strip().lower() for item in boot_compatibility})
        if not compatibility or any(item not in _BOOT_COMPATIBILITY for item in compatibility):
            raise RescueBootError("Boot compatibility must contain bios, uefi, or pi4.")
        secure_boot = secure_boot.strip().lower()
        if secure_boot not in {"supported", "unsupported", "unknown"}:
            raise RescueBootError("Secure Boot metadata must be supported, unsupported, or unknown.")

        source_path = Path(source).expanduser().resolve(strict=True)
        if source_path.is_symlink() or not source_path.is_file():
            raise RescueBootError("Rescue source must be a regular non-symlink file.")
        source_digest = _sha256(source_path)
        if expected_sha256 and source_digest.lower() != expected_sha256.strip().lower():
            raise RescueBootError("Rescue image checksum does not match the expected SHA-256.")

        suffix = source_path.suffix.lower()
        destination = (self.image_directory / f"{image_id}{suffix}").resolve()
        self._assert_within_image_store(destination)
        temporary = destination.with_name(f".{destination.name}.importing")
        if temporary.exists():
            temporary.unlink()
        shutil.copyfile(source_path, temporary)
        try:
            if _sha256(temporary) != source_digest:
                raise RescueBootError("Copied rescue image failed checksum verification.")
            os.chmod(temporary, 0o640)
            os.replace(temporary, destination)
            self._match_parent_ownership(destination)
        finally:
            if temporary.exists():
                temporary.unlink()

        entry = {
            "id": image_id,
            "kind": kind,
            "architecture": architecture,
            "path": str(destination),
            "sha256": source_digest,
            "size_bytes": destination.stat().st_size,
            "boot_compatibility": compatibility,
            "secure_boot": {
                "status": secure_boot,
                "signed": signed,
            },
            "write_mode": write_mode,
            "imported_at": _utc_now(),
        }
        registry = self._load_registry()
        registry["images"] = [
            item for item in registry["images"] if item.get("id") != image_id
        ] + [entry]
        registry["images"].sort(key=lambda item: str(item.get("id", "")))
        self._write_json(self.registry_path, registry, backup=True)
        self._append_history("image.imported", {"image_id": image_id, "sha256": source_digest})
        return dict(entry)

    def arm(
        self,
        mode: str,
        *,
        target_architecture: str | None,
        authorization: str,
        require_hardware: bool = True,
    ) -> dict[str, Any]:
        if authorization != ARM_CONFIRMATION:
            raise RescueBootError("Exact one-shot rescue confirmation is required.")
        self.initialize()
        if not mode.startswith("rescue:"):
            raise RescueBootError("Rescue mode must be rescue:kali, rescue:windows, or rescue:<image-id>.")
        if require_hardware:
            hardware = self.hardware_check()
            if not hardware["ready"]:
                raise RescueBootError("Pi USB rescue hardware is not ready; run rescue hardware-check.")
        image = self._select_image(mode, target_architecture)
        self._verify_image(image)
        pending = {
            "schema_version": 1,
            "mode": mode,
            "image_id": image["id"],
            "image_path": image["path"],
            "sha256": image["sha256"],
            "write_mode": image["write_mode"],
            "armed_at": _utc_now(),
            "target_architecture": image["architecture"],
        }
        self._write_next_boot(pending)
        self._append_history("rescue.armed", {"mode": mode, "image_id": image["id"]})
        return self.status()

    def cancel(self, *, authorization: str) -> dict[str, Any]:
        if authorization != CANCEL_CONFIRMATION:
            raise RescueBootError("Exact rescue cancellation confirmation is required.")
        self.initialize()
        self._write_next_boot(self._normal_state("cancel"))
        self._append_history("rescue.cancelled", {})
        return self.status()

    def consume_early_boot(self) -> dict[str, Any]:
        """Consume pending state after resetting the following boot to normal."""
        self.initialize()
        try:
            pending = self._load_next_boot()
        except RescueBootError as error:
            self._write_next_boot(self._normal_state("invalid-pending-state"))
            self._append_history("rescue.consume_failed", {"error": str(error)})
            raise

        # This reset intentionally occurs before checksum or gadget preparation.
        self._write_next_boot(self._normal_state("early-boot-consumed"))
        if pending["mode"] == "normal":
            if self.active_boot_path.exists():
                self.active_boot_path.unlink()
            self._append_history("boot.normal", {})
            return pending

        consumed = dict(pending)
        consumed["consumed_at"] = _utc_now()
        try:
            image = self._image_by_id(str(consumed["image_id"]))
            self._verify_image(image)
            consumed["image_path"] = image["path"]
            consumed["write_mode"] = image["write_mode"]
            self._write_json(self.active_boot_path, consumed, backup=True)
        except Exception as error:
            if self.active_boot_path.exists():
                self.active_boot_path.unlink()
            self._append_history("rescue.consume_failed", {"error": str(error)})
            raise
        self._append_history("rescue.consumed", {"mode": consumed["mode"], "image_id": consumed["image_id"]})
        return consumed

    def active_image(self) -> dict[str, Any] | None:
        active = self._read_json(self.active_boot_path, default=None)
        if not isinstance(active, dict) or active.get("mode") == "normal":
            return None
        image = self._image_by_id(str(active.get("image_id", "")))
        self._verify_image(image)
        return image

    def reboot_normal(
        self,
        *,
        authorization: str,
        execute: bool,
    ) -> dict[str, Any]:
        if authorization != REBOOT_NORMAL_CONFIRMATION:
            raise RescueBootError("Exact normal reboot confirmation is required.")
        self.initialize()
        self._write_next_boot(self._normal_state("reboot-normal"))
        if self.active_boot_path.exists():
            self.active_boot_path.unlink()
        payload = {"next_pi_boot": "NORMAL BOXBRAIN", "reboot_requested": execute}
        self._append_history("reboot.normal", {"execute": execute})
        if execute:
            self.reboot_runner(["systemctl", "reboot"])
        return payload

    def hardware_check(self) -> dict[str, Any]:
        model_path = self.system_root / "proc/device-tree/model"
        model = ""
        try:
            model = model_path.read_text(encoding="utf-8").replace("\x00", "").strip()
        except OSError:
            pass
        udc_root = self.system_root / "sys/class/udc"
        udcs = sorted(item.name for item in udc_root.iterdir()) if udc_root.is_dir() else []
        configfs = (self.system_root / "sys/kernel/config/usb_gadget").is_dir()
        raw_architecture = platform.machine().strip().lower() or "unknown"
        try:
            architecture = _normalized_architecture(raw_architecture)
        except RescueBootError:
            architecture = raw_architecture
        is_pi4 = "raspberry pi 4" in model.lower()
        return {
            "schema_version": 1,
            "model": model or "unknown",
            "architecture": architecture,
            "pi4": is_pi4,
            "configfs_usb_gadget": configfs,
            "usb_device_controllers": udcs,
            "exactly_one_udc": len(udcs) == 1,
            "ready": is_pi4 and configfs and len(udcs) == 1,
            "actual_boxbrain_filesystem_exported": False,
        }

    def _select_image(self, mode: str, target_architecture: str | None) -> dict[str, Any]:
        selector = mode.split(":", 1)[1]
        if selector not in {"kali", "windows"}:
            return self._image_by_id(selector)
        architecture = _normalized_architecture(target_architecture or "x86_64")
        candidates = [
            item
            for item in self._load_registry()["images"]
            if item.get("kind") == selector
            and item.get("architecture") in {architecture, "multi"}
        ]
        if len(candidates) != 1:
            raise RescueBootError(
                f"Expected exactly one verified {selector} image for {architecture}; found {len(candidates)}."
            )
        return dict(candidates[0])

    def _image_by_id(self, image_id: str) -> dict[str, Any]:
        matches = [item for item in self._load_registry()["images"] if item.get("id") == image_id]
        if len(matches) != 1:
            raise RescueBootError(f"Verified rescue image not found: {image_id}")
        return dict(matches[0])

    def _verify_image(self, image: dict[str, Any]) -> None:
        path = self._validated_image_path(image)
        if _sha256(path) != image.get("sha256"):
            raise RescueBootError(f"Rescue image checksum failed: {image.get('id', 'unknown')}")

    def _validated_image_path(self, image: dict[str, Any]) -> Path:
        raw_path = image.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            raise RescueBootError("Rescue image registry path is invalid.")
        path = Path(raw_path).resolve(strict=True)
        self._assert_within_image_store(path)
        if path.is_symlink() or not path.is_file():
            raise RescueBootError("Registered rescue image is not a regular file.")
        return path

    def _assert_within_image_store(self, path: Path) -> None:
        try:
            path.relative_to(self.image_directory.resolve())
        except ValueError as error:
            raise RescueBootError(
                "Only dedicated rescue image files may be exported; the BoxBrain filesystem is forbidden."
            ) from error

    def _normal_state(self, reason: str) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "mode": "normal",
            "reason": reason,
            "updated_at": _utc_now(),
        }

    def _load_next_boot(self) -> dict[str, Any]:
        payload = self._read_json(self.next_boot_path, default=self._normal_state("missing"))
        if not isinstance(payload, dict):
            raise RescueBootError("Pending rescue state must be a JSON object.")
        mode = payload.get("mode")
        if mode != "normal" and (not isinstance(mode, str) or not mode.startswith("rescue:")):
            raise RescueBootError("Pending rescue mode is invalid.")
        return payload

    def _load_registry(self) -> dict[str, Any]:
        payload = self._read_json(self.registry_path, default={"schema_version": 1, "images": []})
        if not isinstance(payload, dict) or not isinstance(payload.get("images"), list):
            raise RescueBootError("Rescue image registry is invalid.")
        return payload

    def _write_next_boot(self, payload: dict[str, Any]) -> None:
        self._write_json(self.next_boot_path, payload, backup=True)

    def _read_json(self, path: Path, *, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise RescueBootError(f"Could not read {path.name}: {error}") from error

    def _write_json(self, path: Path, payload: Any, *, backup: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        backup_path: Path | None = None
        if backup and path.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            backup_path = self.backup_directory / f"{path.name}.{stamp}.bak"
            shutil.copyfile(path, backup_path)
            os.chmod(backup_path, 0o640)
            self._match_parent_ownership(backup_path)
        temporary = path.with_name(f".{path.name}.tmp")
        try:
            temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.chmod(temporary, 0o640)
            os.replace(temporary, path)
            self._match_parent_ownership(path)
        except Exception:
            if backup_path and backup_path.exists():
                shutil.copyfile(backup_path, path)
            raise
        finally:
            if temporary.exists():
                temporary.unlink()

    def _append_history(self, event: str, details: dict[str, Any]) -> None:
        self.rescue_directory.mkdir(parents=True, exist_ok=True)
        record = {"timestamp": _utc_now(), "event": event, "details": details}
        with self.history_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
        os.chmod(self.history_path, 0o640)
        self._match_parent_ownership(self.history_path)

    @staticmethod
    def _match_parent_ownership(path: Path) -> None:
        """Keep root-run CLI output readable by the BoxBrain service account."""
        get_effective_uid = getattr(os, "geteuid", None)
        change_owner = getattr(os, "chown", None)
        if get_effective_uid is None or change_owner is None or get_effective_uid() != 0:
            return
        parent = path.parent.stat()
        change_owner(path, parent.st_uid, parent.st_gid)

    @staticmethod
    def _run_reboot(command: list[str]) -> Any:
        return subprocess.run(command, check=True, timeout=15)
