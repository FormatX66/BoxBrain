#!/usr/bin/env python3
"""Secret-safe Wi-Fi persistence proof for normal Aurum generations.

The updater never copies a credential into Git or a public receipt. It records
only opaque path identities, content hashes, sizes, and modes for the existing
Aurum, NetworkManager, and wpa_supplicant profiles, then requires those exact
fingerprints and an already-online route to survive the runtime apply.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "aurum.wifi-persistence.v1"
DEFAULT_STATE = Path(os.environ.get("AURUM_STATE_DIR", "/var/lib/aurum/state"))
DEFAULT_SYSTEM_ROOT = Path(os.environ.get("AURUM_SYSTEM_ROOT", "/"))


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
        "secret_material_in_receipt": False,
    }


def verify(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    before_profiles = list(before.get("profiles") or [])
    after_profiles = list(after.get("profiles") or [])
    profiles_unchanged = before_profiles == after_profiles
    configured_retained = not bool(before.get("configured")) or bool(after.get("configured"))
    before_network = before.get("network") if isinstance(before.get("network"), Mapping) else {}
    after_network = after.get("network") if isinstance(after.get("network"), Mapping) else {}
    online_retained = not bool(before_network.get("online")) or bool(after_network.get("online"))
    interface_retained = (
        not before_network.get("online")
        or not before_network.get("interface")
        or before_network.get("interface") == after_network.get("interface")
    )
    passed = bool(profiles_unchanged and configured_retained and online_retained and interface_retained)
    return {
        "schema": SCHEMA,
        "status": "passed" if passed else "failed",
        "profiles_unchanged": profiles_unchanged,
        "configured_retained": configured_retained,
        "online_retained": online_retained,
        "interface_retained": interface_retained,
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
