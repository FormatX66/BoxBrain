"""Persistent computers and their changing BoxBrain connection paths."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any


TARGET_ID_PATTERN = re.compile(r"^BB-TARGET-[A-Z0-9][A-Z0-9-]{5,63}$")


def load_node_preferences(state_directory: str) -> dict[str, Any]:
    """Load operator-only node presentation preferences."""

    path = Path(state_directory) / "operator" / "node.json"
    return _read_dict(path) or {"archived": False}


def set_node_archived(state_directory: str, archived: bool) -> dict[str, Any]:
    """Hide or restore this node without deleting its state or connections."""

    path = Path(state_directory) / "operator" / "node.json"
    preferences = load_node_preferences(state_directory)
    preferences["archived"] = bool(archived)
    preferences["updated_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_write(path, preferences)
    return preferences


def _identity_key(item: dict[str, Any]) -> str:
    for key in ("machine_id", "machine_guid_hash", "device_id", "hostname"):
        value = str(item.get(key, "")).strip().lower()
        if value:
            return f"{key}:{value}"
    existing = str(item.get("target_id", "")).strip().upper()
    if TARGET_ID_PATTERN.fullmatch(existing):
        return f"target_id:{existing}"
    return f"legacy-address:{str(item.get('address') or 'unknown').strip().lower()}"


def target_id_for(item: dict[str, Any]) -> str:
    """Return a permanent public ID derived from machine identity, never its IP."""

    identity = _identity_key(item)
    if identity.startswith("target_id:"):
        return identity.removeprefix("target_id:")
    digest = hashlib.sha256(identity.split(":", 1)[1].encode("utf-8")).hexdigest()[:10]
    return f"BB-TARGET-{digest.upper()}"


def friendly_name_for(item: dict[str, Any]) -> str:
    nickname = str(item.get("nickname", "")).strip()
    if nickname:
        return nickname
    hostname = str(item.get("hostname", "")).strip()
    return hostname or "Remembered computer"


def _normalized(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    normalized["identity_key"] = _identity_key(item)
    normalized["target_id"] = target_id_for(item)
    normalized["friendly_name"] = friendly_name_for(item)
    connections = normalized.get("connections")
    normalized["connections"] = connections if isinstance(connections, list) else []
    return normalized


def load_links(state_directory: str) -> list[dict[str, Any]]:
    """Load active/historical link observations retained for compatibility."""

    links_directory = Path(state_directory) / "links"
    links: list[dict[str, Any]] = []
    try:
        paths = sorted(links_directory.glob("*.json"))
    except OSError:
        return links
    for path in paths:
        item = _read_dict(path)
        if item is not None:
            links.append(_normalized(item))
    return links


def load_computers(state_directory: str) -> list[dict[str, Any]]:
    """Load the persistent fleet, importing link observations by machine identity."""

    grouped_links: dict[str, list[dict[str, Any]]] = {}
    for link in load_links(state_directory):
        grouped_links.setdefault(str(link["target_id"]), []).append(link)
    for observations in grouped_links.values():
        current = max(observations, key=_observation_priority)
        combined = dict(current)
        connections: list[dict[str, Any]] = []
        for observation in observations:
            observed_values = observation.get("connections", [])
            if isinstance(observed_values, list):
                connections.extend(
                    value for value in observed_values if isinstance(value, dict)
                )
            observed_connection = _connection_from_observation(observation)
            if observed_connection is not None:
                connections.append(observed_connection)
        combined["connections"] = connections
        try:
            record_computer(state_directory, combined)
        except OSError:
            pass
    computers: list[dict[str, Any]] = []
    directory = Path(state_directory) / "computers"
    try:
        paths = sorted(directory.glob("BB-TARGET-*.json"))
    except OSError:
        return computers
    for path in paths:
        item = _read_dict(path)
        if item is not None:
            computers.append(_normalized(item))
    return computers


def find_link(state_directory: str, target_id: str) -> dict[str, Any] | None:
    """Compatibility alias: operator workspaces now resolve persistent computers."""

    return find_computer(state_directory, target_id)


def find_computer(state_directory: str, target_id: str) -> dict[str, Any] | None:
    normalized_id = target_id.strip().upper()
    for item in load_computers(state_directory):
        if item["target_id"] == normalized_id:
            return item
    return None


def set_computer_archived(
    state_directory: str,
    target_id: str,
    archived: bool,
) -> dict[str, Any]:
    """Hide or restore a persistent computer without losing history."""

    computer = find_computer(state_directory, target_id)
    if computer is None:
        raise KeyError(target_id)
    computer["archived"] = bool(archived)
    computer["archived_at"] = (
        datetime.now(timezone.utc).isoformat() if archived else None
    )
    return record_computer(state_directory, computer)


def record_computer(state_directory: str, observation: dict[str, Any]) -> dict[str, Any]:
    """Merge an observation into a computer record without making its address its ID."""

    incoming = _normalized(observation)
    target_id = str(incoming["target_id"])
    directory = Path(state_directory) / "computers"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{target_id}.json"
    existing = _read_dict(destination) or {}

    merged = dict(existing)
    for key, value in incoming.items():
        if key in {"connections", "friendly_name"}:
            continue
        if value not in (None, "", [], {}):
            merged[key] = value
    if existing.get("nickname") and not observation.get("nickname"):
        merged["nickname"] = existing["nickname"]
    merged["identity_key"] = _identity_key(incoming)
    merged["target_id"] = target_id
    merged["friendly_name"] = friendly_name_for(merged)

    connection_values: list[dict[str, Any]] = []
    old_connections = existing.get("connections", [])
    if isinstance(old_connections, list):
        connection_values.extend(value for value in old_connections if isinstance(value, dict))
    new_connections = incoming.get("connections", [])
    if isinstance(new_connections, list):
        connection_values.extend(value for value in new_connections if isinstance(value, dict))
    observed_connection = _connection_from_observation(incoming)
    if observed_connection is not None:
        connection_values.append(observed_connection)
    merged["connections"] = _merge_connections(connection_values)
    merged["status"] = _computer_status(merged)
    _atomic_write(destination, merged)
    return _normalized(merged)


def remember_discovered_computer(
    state_directory: str,
    *,
    hostname: str,
    address: str,
    open_ports: list[int],
    nickname: str | None = None,
) -> dict[str, Any]:
    """Remember a bounded private-LAN discovery and its available setup choices."""

    now = datetime.now(timezone.utc).isoformat()
    port_set = {int(value) for value in open_ports}
    connections: list[dict[str, Any]] = [
        {
            "id": "local-network",
            "friendly_name": "Local",
            "connection_type": "local-network",
            "description": "Detected on the local private network",
            "status": "available",
            "address": address,
            "last_seen_at": now,
        },
        {
            "id": "winrm",
            "friendly_name": "WinRM",
            "connection_type": "winrm",
            "description": "Windows remote management on the private network",
            "status": "available" if port_set.intersection({5985, 5986}) else "setup-required",
            "address": address,
            "ports": sorted(port_set.intersection({5985, 5986})),
            "last_seen_at": now,
        },
        {
            "id": "remote-desktop",
            "friendly_name": "Remote Desktop",
            "connection_type": "rdp",
            "description": "Windows desktop on the private network",
            "status": "available" if 3389 in port_set else "setup-required",
            "address": address,
            "ports": [3389] if 3389 in port_set else [],
            "last_seen_at": now,
        },
        {
            "id": "direct-boxlink",
            "friendly_name": "Direct BoxLink",
            "connection_type": "outbound-boxlink",
            "description": "Target-owned outbound path that does not depend on this Pi",
            "status": "setup-required",
            "last_seen_at": now,
        },
    ]
    return record_computer(
        state_directory,
        {
            "hostname": hostname,
            "nickname": nickname or "",
            "address": address,
            "platform": "Windows",
            "status": "detected",
            "last_checked": now,
            "last_seen": int(datetime.now(timezone.utc).timestamp()),
            "discovery_ports": sorted(port_set),
            "connections": connections,
        },
    )


def update_link_profile(
    state_directory: str,
    target_id: str,
    *,
    nickname: str,
) -> dict[str, Any]:
    """Persist a friendly name independently of every current connection path."""

    normalized_id = target_id.strip().upper()
    clean_name = " ".join(nickname.split())
    if not 1 <= len(clean_name) <= 80:
        raise ValueError("Computer nickname must be between 1 and 80 characters.")
    if any(ord(character) < 32 for character in clean_name):
        raise ValueError("Computer nickname contains unsupported characters.")
    computer = find_computer(state_directory, normalized_id)
    if computer is None:
        raise KeyError(normalized_id)
    computer["nickname"] = clean_name
    updated = record_computer(state_directory, computer)
    for path in _matching_link_paths(state_directory, normalized_id):
        item = _read_dict(path)
        if item is not None:
            item["target_id"] = normalized_id
            item["nickname"] = clean_name
            _atomic_write(path, item)
    return updated


def update_link_connection(
    state_directory: str,
    target_id: str,
    *,
    status: str,
    last_checked: str,
    last_seen: int | None = None,
    address: str = "",
) -> dict[str, Any]:
    """Persist an authenticated connection result on its computer and link record."""

    if status not in {"connected", "offline"}:
        raise ValueError("Unsupported BoxBrain connection status.")
    normalized_id = target_id.strip().upper()
    computer = find_computer(state_directory, normalized_id)
    if computer is None:
        raise KeyError(normalized_id)
    current_address = address.strip() or str(computer.get("address", "")).strip()
    computer["status"] = status
    computer["last_checked"] = last_checked
    if last_seen is not None:
        computer["last_seen"] = last_seen
    connections = computer.get("connections", [])
    for connection in connections if isinstance(connections, list) else []:
        if isinstance(connection, dict) and connection.get("connection_type") in {
            "ssh", "boxlink-ssh"
        } and (
            not current_address
            or str(connection.get("address", "")).strip() == current_address
        ):
            connection["status"] = "available" if status == "connected" else "unavailable"
            connection["last_seen_at"] = last_checked
    updated = record_computer(state_directory, computer)
    for path in _matching_link_paths(state_directory, normalized_id):
        item = _read_dict(path)
        if item is None or (
            current_address
            and str(item.get("address", "")).strip() != current_address
        ):
            continue
        item["target_id"] = normalized_id
        item["status"] = status
        item["last_checked"] = last_checked
        if last_seen is not None:
            item["last_seen"] = last_seen
        _atomic_write(path, item)
    return updated


def update_saved_connection(
    state_directory: str,
    target_id: str,
    *,
    connection_type: str,
    status: str,
    last_checked: str,
    error: str = "",
    connection_id: str = "",
) -> dict[str, Any]:
    """Update one persistent connection path without hiding other usable paths."""

    if status not in {"available", "unavailable", "degraded"}:
        raise ValueError("Unsupported saved connection status.")
    normalized_id = target_id.strip().upper()
    computer = find_computer(state_directory, normalized_id)
    if computer is None:
        raise KeyError(normalized_id)
    connections = computer.get("connections", [])
    if not isinstance(connections, list):
        raise KeyError(connection_type)
    matched = False
    for connection in connections:
        if (
            isinstance(connection, dict)
            and connection.get("connection_type") == connection_type
            and (
                not connection_id
                or str(connection.get("id", "")) == connection_id
            )
        ):
            connection["status"] = status
            connection["last_seen_at"] = last_checked
            connection["last_verified_at"] = last_checked
            connection["last_error"] = error[:300]
            matched = True
    if not matched:
        raise KeyError(connection_type)
    updated = record_computer(state_directory, computer)
    for path in _matching_link_paths(state_directory, normalized_id):
        item = _read_dict(path)
        if item is None:
            continue
        link_connections = item.get("connections", [])
        if not isinstance(link_connections, list):
            continue
        for connection in link_connections:
            if (
                isinstance(connection, dict)
                and connection.get("connection_type") == connection_type
                and (
                    not connection_id
                    or str(connection.get("id", "")) == connection_id
                )
            ):
                connection["status"] = status
                connection["last_seen_at"] = last_checked
                connection["last_verified_at"] = last_checked
                connection["last_error"] = error[:300]
        _atomic_write(path, item)
    return updated


def _connection_from_observation(item: dict[str, Any]) -> dict[str, Any] | None:
    address = str(item.get("address", "")).strip()
    transport = str(item.get("transport", "")).strip()
    if not address or not transport:
        return None
    target_id = target_id_for(item)
    suffix = hashlib.sha256(f"{transport}:{address}".encode("utf-8")).hexdigest()[:8]
    available = str(item.get("status", "offline")).lower() in {"connected", "online", "available"}
    return {
        "id": f"{target_id}-{suffix.upper()}",
        "friendly_name": "BoxLink" if "ssh" in transport else "Local",
        "connection_type": "boxlink-ssh" if "ssh" in transport else transport,
        "description": "Authorized managed connection",
        "status": "available" if available else "unavailable",
        "address": address,
        "transport": transport,
        "interface": item.get("interface"),
        "last_seen_at": item.get("last_checked"),
    }


def _observation_priority(item: dict[str, Any]) -> tuple[int, float]:
    status = str(item.get("status", "offline")).lower()
    status_priority = {
        "connected": 4,
        "online": 3,
        "available": 3,
        "detected": 2,
        "degraded": 1,
        "offline": 0,
        "unavailable": 0,
    }.get(status, 0)
    timestamp = item.get("last_seen")
    if isinstance(timestamp, (int, float)):
        return status_priority, float(timestamp)
    checked = str(item.get("last_checked", "")).strip()
    if checked:
        try:
            return status_priority, datetime.fromisoformat(
                checked.replace("Z", "+00:00")
            ).timestamp()
        except (ValueError, OverflowError, OSError):
            pass
    return status_priority, 0.0


def _merge_connections(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for value in values:
        connection_id = str(value.get("id", "")).strip()
        if not connection_id:
            basis = f"{value.get('connection_type')}:{value.get('address')}"
            connection_id = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:12]
        current = merged.get(connection_id, {})
        current.update({key: item for key, item in value.items() if item is not None})
        current["id"] = connection_id
        merged[connection_id] = current
    return sorted(
        merged.values(),
        key=lambda item: (
            item.get("status") not in {"available", "connected"},
            str(item.get("friendly_name", "")),
        ),
    )


def _computer_status(item: dict[str, Any]) -> str:
    requested = str(item.get("status", "offline")).lower()
    connections = item.get("connections", [])
    if isinstance(connections, list) and any(
        isinstance(value, dict) and value.get("status") in {"available", "connected"}
        for value in connections
    ):
        return "connected" if requested == "connected" else "online"
    if requested in {"connected", "online", "detected"}:
        return requested
    return "offline"


def _matching_link_paths(state_directory: str, target_id: str) -> list[Path]:
    matches: list[Path] = []
    for path in sorted((Path(state_directory) / "links").glob("*.json")):
        item = _read_dict(path)
        if item is not None and target_id_for(item) == target_id:
            matches.append(path)
    return matches


def _read_dict(path: Path) -> dict[str, Any] | None:
    try:
        item = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return item if isinstance(item, dict) else None


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
