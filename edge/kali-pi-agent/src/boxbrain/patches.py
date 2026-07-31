"""Checksum-gated patch staging for explicitly authorized target links."""

from __future__ import annotations

from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Callable

from boxbrain.drive_sync import SAFE_COMPONENT, _atomic_json, sha256_file
from boxbrain.links import load_links


PATCH_DELIVERY_AUTHORIZATION = "I am authorized to deliver this patch"
PATCH_DELIVERY_CONFIRMATION = "DELIVER PATCH"
SAFE_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")


class PatchDeliveryError(RuntimeError):
    """Raised when a patch cannot be safely staged on a linked target."""


def _sftp_quote(value: str) -> str:
    if any(character in value for character in "\r\n\x00"):
        raise PatchDeliveryError("Patch path contains unsupported characters.")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class PatchManager:
    def __init__(
        self,
        state_directory: str,
        identity_file: str = "/var/lib/boxbrain/identity/target_ed25519",
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.state_directory = Path(state_directory)
        self.identity_file = Path(identity_file)
        self.known_hosts = self.state_directory / "identity" / "target_known_hosts"
        self.patch_directory = self.state_directory / "drive" / "patches"
        self.runner = runner

    def _load(self, reference: str) -> tuple[dict[str, Any], Path, Path]:
        if not SAFE_REFERENCE.fullmatch(reference):
            raise PatchDeliveryError("Patch reference is invalid.")
        directory = self.patch_directory / "verified" / reference
        if directory.is_symlink() or not directory.is_dir():
            raise PatchDeliveryError("Verified patch directory is unavailable.")
        manifest_path = directory / "manifest.json"
        if manifest_path.is_symlink():
            raise PatchDeliveryError("Verified patch manifest is unsafe.")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise PatchDeliveryError("Verified patch manifest is unavailable.") from error
        if not isinstance(manifest, dict):
            raise PatchDeliveryError("Verified patch manifest is invalid.")
        payload_name = str(manifest.get("payload", ""))
        if not SAFE_COMPONENT.fullmatch(payload_name):
            raise PatchDeliveryError("Verified patch payload name is invalid.")
        payload_path = directory / payload_name
        if (
            payload_path.parent != directory
            or payload_path.is_symlink()
            or not payload_path.is_file()
        ):
            raise PatchDeliveryError("Verified patch payload is unavailable.")
        if sha256_file(payload_path) != manifest.get("sha256"):
            raise PatchDeliveryError("Verified patch checksum changed after staging.")
        return manifest, manifest_path, payload_path

    def list(self) -> list[dict[str, Any]]:
        verified = self.patch_directory / "verified"
        patches: list[dict[str, Any]] = []
        try:
            references = sorted(path for path in verified.iterdir() if path.is_dir())
        except FileNotFoundError:
            return patches
        for directory in references:
            try:
                manifest, _manifest_path, _payload_path = self._load(directory.name)
            except PatchDeliveryError:
                continue
            patches.append(
                {
                    "reference": directory.name,
                    "patch_id": manifest.get("patch_id"),
                    "target_hostname": manifest.get("target_hostname"),
                    "payload": manifest.get("payload"),
                    "sha256": manifest.get("sha256"),
                    "size_bytes": manifest.get("size_bytes"),
                    "verified_at": manifest.get("verified_at"),
                }
            )
        return patches

    def deliver(
        self,
        reference: str,
        authorization: str,
        confirmation: str,
    ) -> dict[str, Any]:
        if authorization != PATCH_DELIVERY_AUTHORIZATION:
            raise PatchDeliveryError("Explicit target authorization is required.")
        if confirmation != PATCH_DELIVERY_CONFIRMATION:
            raise PatchDeliveryError(f"Confirmation must be {PATCH_DELIVERY_CONFIRMATION!r}.")
        if not self.identity_file.is_file() or not self.known_hosts.is_file():
            raise PatchDeliveryError("Target SSH identity is not ready.")

        manifest, manifest_path, payload_path = self._load(reference)
        target_hostname = str(manifest.get("target_hostname", ""))
        matches = [
            item
            for item in load_links(str(self.state_directory))
            if str(item.get("hostname", "")).casefold() == target_hostname.casefold()
            and item.get("status") == "connected"
        ]
        if len(matches) != 1:
            raise PatchDeliveryError(
                "Patch target must match exactly one connected authorized hostname."
            )
        address = str(matches[0].get("address", ""))
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError as error:
            raise PatchDeliveryError("Authorized target address is invalid.") from error
        if parsed.version != 4 or not (parsed.is_private or parsed.is_link_local):
            raise PatchDeliveryError("Patch delivery requires a private target IPv4 address.")

        remote_payload = f"{reference}--{payload_path.name}"
        remote_manifest = f"{reference}--manifest.json"
        batch = "\n".join(
            (
                "-mkdir BoxBrain",
                "-mkdir BoxBrain/Patches",
                "-mkdir BoxBrain/Patches/incoming",
                f"put {_sftp_quote(str(payload_path))} {_sftp_quote('BoxBrain/Patches/incoming/' + remote_payload)}",
                f"put {_sftp_quote(str(manifest_path))} {_sftp_quote('BoxBrain/Patches/incoming/' + remote_manifest)}",
                "",
            )
        )
        command = [
            "sftp",
            "-b",
            "-",
            "-i",
            str(self.identity_file),
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=5",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={self.known_hosts}",
            f"boxbrain-link@{address}",
        ]
        try:
            result = self.runner(
                command,
                input=batch,
                check=False,
                capture_output=True,
                text=True,
                timeout=180,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise PatchDeliveryError(f"Patch transfer could not start: {error}") from error
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            message = detail[-1] if detail else "unknown SFTP failure"
            raise PatchDeliveryError(f"Patch transfer failed: {message[:500]}")

        receipt = {
            "schema_version": 1,
            "status": "delivered-not-executed",
            "delivered_at": datetime.now(timezone.utc).isoformat(),
            "reference": reference,
            "patch_id": manifest.get("patch_id"),
            "target_hostname": target_hostname,
            "target_address": address,
            "payload": remote_payload,
            "sha256": manifest.get("sha256"),
        }
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        receipt_name = re.sub(r"[^A-Za-z0-9_.-]", "-", f"{reference}-{stamp}.json")
        _atomic_json(self.patch_directory / "receipts" / receipt_name, receipt)
        return receipt
