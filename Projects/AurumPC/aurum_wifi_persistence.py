#!/usr/bin/env python3
"""Secret-safe, cross-reboot Wi-Fi persistence proof for Aurum generations.

The updater never copies a credential into Git or a public receipt. It records
only opaque path identities, content hashes, sizes, and modes for the existing
Aurum, NetworkManager, and wpa_supplicant profiles. Promotion additionally
requires the state path to live on durable storage; a live overlay can prove a
same-session apply but cannot falsely claim that credentials survive reboot.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

SCHEMA = "aurum.wifi-persistence.v1"
DEFAULT_STATE = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
DEFAULT_SYSTEM_ROOT = Path(os.environ.get("AURUM_SYSTEM_ROOT", "/"))
VOLATILE_FILESYSTEMS = {"aufs", "overlay", "ramfs", "squashfs", "tmpfs"}


def _boot_identity(path: Path = Path("/proc/sys/kernel/random/boot_id")) -> str | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else None


def _unescape_mount(value: str) -> str:
    return (
        value.replace("\\040", " ")
        .replace("\\011", "\t")
        .replace("\\012", "\n")
        .replace("\\134", "\\")
    )


def storage_evidence(
    path: Path,
    *,
    mountinfo_path: Path = Path("/proc/self/mountinfo"),
) -> dict[str, Any]:
    """Describe the longest mount containing *path* without writing storage."""
    try:
        path_text = path.as_posix()
        if not path_text.startswith("/"):
            path_text = path.resolve().as_posix()
        resolved = PurePosixPath(path_text)
        lines = mountinfo_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return {
            "status": "unknown",
            "cross_boot_capable": False,
            "reason": f"mount-evidence-unavailable:{type(exc).__name__}",
        }
    candidates: list[tuple[int, Path, str, str]] = []
    for line in lines:
        fields = line.split()
        if "-" not in fields or len(fields) < 7:
            continue
        separator = fields.index("-")
        if separator + 2 >= len(fields):
            continue
        mountpoint = PurePosixPath(_unescape_mount(fields[4]))
        try:
            resolved.relative_to(mountpoint)
        except ValueError:
            continue
        candidates.append((len(mountpoint.parts), mountpoint, fields[separator + 1], fields[separator + 2]))
    if not candidates:
        return {
            "status": "unknown",
            "cross_boot_capable": False,
            "reason": "state-path-mount-not-found",
        }
    _depth, mountpoint, filesystem, source = max(candidates, key=lambda item: item[0])
    durable = filesystem not in VOLATILE_FILESYSTEMS and source not in {"overlay", "tmpfs"}
    return {
        "status": "durable" if durable else "volatile",
        "cross_boot_capable": durable,
        "filesystem": filesystem,
        "mountpoint": str(mountpoint),
        "source_kind": "block-or-persistent" if durable else "live-or-memory",
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _identity(kind: str, path: Path) -> str:
    # Profile filenames can contain an SSID. Keep only a stable opaque identity
    # in receipts so the proof cannot disclose the network name.
    return hashlib.sha256(f"{kind}\0{path}".encode("utf-8", "surrogatepass")).hexdigest()


def _profile(kind: str, path: Path) -> dict[str, Any] | None:
    try:
        stat = path.stat()
        content = _sha256(path)
    except OSError:
        return None
    if not path.is_file():
        return None
    return {
        "kind": kind,
        "identity_sha256": _identity(kind, path),
        "content_sha256": content,
        "size": stat.st_size,
        "mode": stat.st_mode & 0o777,
    }


def capture(
    *,
    state_dir: Path = DEFAULT_STATE,
    system_root: Path = DEFAULT_SYSTEM_ROOT,
    network: Mapping[str, Any] | None = None,
    storage: Mapping[str, Any] | None = None,
    boot_identity_sha256: str | None = None,
) -> dict[str, Any]:
    profiles: list[dict[str, Any]] = []
    candidates: list[tuple[str, Path]] = [("aurum", state_dir / "wifi.conf")]
    candidates.extend(
        ("networkmanager", path)
        for path in sorted(
            (system_root / "etc/NetworkManager/system-connections").glob("*.nmconnection")
        )
    )
    candidates.extend(
        ("wpa-supplicant", path)
        for path in sorted((system_root / "etc/wpa_supplicant").glob("*.conf"))
    )
    for kind, path in candidates:
        item = _profile(kind, path)
        if item is not None:
            profiles.append(item)
    profiles.sort(key=lambda item: (str(item["kind"]), str(item["identity_sha256"])))
    counts = Counter(str(item["kind"]) for item in profiles)
    network_value = dict(network or {})
    storage_value = dict(storage) if storage is not None else storage_evidence(state_dir)
    return {
        "schema": SCHEMA,
        "configured": bool(profiles),
        "profile_count": len(profiles),
        "profile_kinds": dict(sorted(counts.items())),
        "profiles": profiles,
        "network": {
            "online": bool(network_value.get("online")),
            "interface": str(network_value.get("interface") or "") or None,
            "wireless_interface_count": len(network_value.get("wireless_interfaces") or []),
        },
        "storage": storage_value,
        "boot_identity_sha256": boot_identity_sha256 or _boot_identity(),
        "secret_material_in_receipt": False,
    }


def verify(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    before_profiles = list(before.get("profiles") or [])
    after_profiles = list(after.get("profiles") or [])
    profiles_unchanged = before_profiles == after_profiles
    configured_retained = bool(before.get("configured") and after.get("configured"))
    before_network = before.get("network") if isinstance(before.get("network"), Mapping) else {}
    after_network = after.get("network") if isinstance(after.get("network"), Mapping) else {}
    online_retained = bool(before_network.get("online") and after_network.get("online"))
    interface_retained = (
        not before_network.get("online")
        or not before_network.get("interface")
        or before_network.get("interface") == after_network.get("interface")
    )
    before_storage = before.get("storage") if isinstance(before.get("storage"), Mapping) else {}
    after_storage = after.get("storage") if isinstance(after.get("storage"), Mapping) else {}
    cross_boot_capable = bool(
        before_storage.get("cross_boot_capable") and after_storage.get("cross_boot_capable")
    )
    before_boot = before.get("boot_identity_sha256")
    after_boot = after.get("boot_identity_sha256")
    reboot_observed = bool(before_boot and after_boot and before_boot != after_boot)
    same_session_passed = bool(
        profiles_unchanged and configured_retained and online_retained and interface_retained
    )
    existing_profile_lost = bool(before.get("configured") and not after.get("configured"))
    existing_online_lost = bool(before_network.get("online") and not after_network.get("online"))
    if not profiles_unchanged or existing_profile_lost or existing_online_lost or not interface_retained:
        status = "failed"
    elif not configured_retained:
        status = "pending-wifi-profile"
    elif not online_retained:
        status = "pending-wifi-online"
    elif not cross_boot_capable and same_session_passed:
        status = "pending-reboot-storage"
    elif same_session_passed and cross_boot_capable and not reboot_observed:
        status = "pending-reboot-observation"
    elif same_session_passed and cross_boot_capable and reboot_observed:
        status = "passed"
    else:
        status = "failed"
    return {
        "schema": SCHEMA,
        "status": status,
        "profiles_unchanged": profiles_unchanged,
        "configured_retained": configured_retained,
        "online_retained": online_retained,
        "interface_retained": interface_retained,
        "same_session_passed": same_session_passed,
        "cross_boot_capable": cross_boot_capable,
        "reboot_observed": reboot_observed,
        "before": dict(before),
        "after": dict(after),
        "secret_material_in_receipt": False,
    }


def write_receipt(path: Path, proof: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(dict(proof), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
