"""Outbound-only, local-first synchronization with the BoxBrain server."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import socket
import sqlite3
import time
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener
import uuid

from boxbrain.diagnostics import DIAGNOSTIC_AUTHORIZATION, TargetDiagnostics
from boxbrain.links import find_computer, load_computers

LOG = logging.getLogger("boxbrain.sync")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SyncConfigurationError(ValueError):
    pass


class SyncTransportError(RuntimeError):
    pass


class SyncStore:
    """Durable outbound event queue, target IDs, and inbound action inbox."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.initialize()

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS sync_events (
                    id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_id TEXT,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS target_identities (
                    source_key TEXT PRIMARY KEY,
                    target_id TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS inbound_actions (
                    id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS sync_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def target_id(self, source_key: str) -> str:
        stable_key = " ".join(source_key.strip().lower().split())
        if not stable_key:
            raise ValueError("target identity source key must not be empty")
        with self._connection() as connection:
            row = connection.execute(
                "SELECT target_id FROM target_identities WHERE source_key = ?",
                (stable_key,),
            ).fetchone()
            if row:
                return str(row["target_id"])
            suffix = hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:12].upper()
            target_id = f"BB-TARGET-{suffix}"
            connection.execute(
                """
                INSERT INTO target_identities (source_key, target_id, created_at)
                VALUES (?, ?, ?)
                """,
                (stable_key, target_id, utc_now()),
            )
        return target_id

    def enqueue_event(
        self,
        *,
        event_type: str,
        source_type: str,
        source_id: str | None,
        message: str,
        level: str = "info",
        details: dict[str, object] | None = None,
    ) -> str:
        event_id = str(uuid.uuid4())
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO sync_events (
                    id, event_type, source_type, source_id, level, message,
                    details_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    event_type,
                    source_type,
                    source_id,
                    level,
                    message,
                    json.dumps(details or {}, separators=(",", ":")),
                    utc_now(),
                ),
            )
        return event_id

    def pending_events(self, *, limit: int = 200) -> list[dict[str, object]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM sync_events ORDER BY created_at ASC LIMIT ?
                """,
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "event_type": row["event_type"],
                "source_type": row["source_type"],
                "source_id": row["source_id"],
                "level": row["level"],
                "message": row["message"],
                "details": json.loads(row["details_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def acknowledge_events(self, event_ids: list[str]) -> None:
        if not event_ids:
            return
        with self._connection() as connection:
            connection.executemany(
                "DELETE FROM sync_events WHERE id = ?",
                [(event_id,) for event_id in event_ids],
            )

    def note_failed_attempt(self, event_ids: list[str]) -> None:
        if not event_ids:
            return
        with self._connection() as connection:
            connection.executemany(
                "UPDATE sync_events SET attempts = attempts + 1 WHERE id = ?",
                [(event_id,) for event_id in event_ids],
            )

    def record_actions(self, actions: list[dict[str, object]]) -> list[str]:
        received: list[str] = []
        with self._connection() as connection:
            for action in actions:
                action_id = str(action.get("id", "")).strip()
                if not action_id:
                    continue
                inserted = connection.execute(
                    """
                    INSERT OR IGNORE INTO inbound_actions (
                        id, payload_json, status, received_at
                    ) VALUES (?, ?, 'pending', ?)
                    """,
                    (
                        action_id,
                        json.dumps(action, separators=(",", ":")),
                        utc_now(),
                    ),
                ).rowcount
                if inserted:
                    received.append(action_id)
        return received

    def pending_actions(self) -> list[dict[str, object]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM inbound_actions
                WHERE status = 'pending' ORDER BY received_at ASC
                """
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def complete_action(self, action_id: str, status: str) -> None:
        if status not in {"succeeded", "failed", "cancelled"}:
            raise ValueError("Invalid completed action status.")
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE inbound_actions SET status=?, completed_at=? WHERE id=?
                """,
                (status, utc_now(), action_id),
            )

    def set_state(self, key: str, value: str) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO sync_state (key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                  value=excluded.value, updated_at=excluded.updated_at
                """,
                (key, value, utc_now()),
            )

    def get_state(self, key: str) -> str | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT value FROM sync_state WHERE key = ?", (key,)
            ).fetchone()
        return str(row["value"]) if row else None

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()


class BoxBrainSyncClient:
    def __init__(
        self,
        *,
        server_url: str,
        node_token: str,
        node_id: str,
        node_name: str,
        local_api_url: str,
        store: SyncStore,
        timeout_seconds: float = 10,
        state_directory: str | Path | None = None,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.node_token = node_token
        self.node_id = node_id.strip().upper()
        self.node_name = node_name.strip()
        self.local_api_url = local_api_url.rstrip("/")
        self.store = store
        self.timeout_seconds = timeout_seconds
        self.state_directory = (
            Path(state_directory) if state_directory is not None else None
        )
        self._validate_configuration()
        self._opener = build_opener()

    def _validate_configuration(self) -> None:
        server = urlsplit(self.server_url)
        is_loopback = server.hostname in {"127.0.0.1", "localhost", "::1"}
        if server.scheme != "https" and not (server.scheme == "http" and is_loopback):
            raise SyncConfigurationError(
                "BoxBrain server sync requires HTTPS except for loopback tests."
            )
        local = urlsplit(self.local_api_url)
        if local.scheme != "http" or local.hostname not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            raise SyncConfigurationError("The Pi local API must remain loopback-only.")
        if len(self.node_token) < 32:
            raise SyncConfigurationError("The node sync token must be at least 32 characters.")
        if not self.node_id.startswith("BB-NODE-"):
            raise SyncConfigurationError("The node ID must use the BB-NODE- prefix.")

    def run_once(self) -> dict[str, object]:
        status = self._get_local_json("/api/v1/status")
        jobs_payload = self._get_local_json("/api/v1/jobs")
        snapshot = self.build_snapshot(status, jobs_payload.get("jobs", []))
        event_ids = [str(item["id"]) for item in snapshot["events"]]
        try:
            response = self._post_server_json("/api/v1/node-sync/snapshot", snapshot)
        except SyncTransportError:
            self.store.note_failed_attempt(event_ids)
            self.store.set_state("server_connection", "disconnected")
            raise
        accepted = [str(value) for value in response.get("accepted_event_ids", [])]
        self.store.acknowledge_events(accepted)
        actions = response.get("actions", [])
        if not isinstance(actions, list):
            actions = []
        received_action_ids = self.store.record_actions(
            [item for item in actions if isinstance(item, dict)]
        )
        self.store.set_state("server_connection", "connected")
        self.store.set_state("last_sync_at", utc_now())
        for action_id in received_action_ids:
            self.store.enqueue_event(
                event_type="action.received",
                source_type="action",
                source_id=action_id,
                message="Confirmed server action was stored in the local inbox.",
                details={"node_id": self.node_id},
            )
        return response

    def execute_pending_actions(self, state_directory: str | Path) -> list[str]:
        """Execute a small read-only allowlist received through the node path."""

        completed: list[str] = []
        diagnostics = TargetDiagnostics(str(state_directory))
        for action in self.store.pending_actions():
            action_id = str(action.get("id", ""))
            action_type = str(action.get("action_type", ""))
            target_id = str(action.get("computer_id", ""))
            result: dict[str, object]
            status = "succeeded"
            try:
                if action_type == "collect_status":
                    result = self._get_local_json("/api/v1/status")
                elif action_type in {"probe_connection", "run_diagnostics"}:
                    computer = find_computer(str(state_directory), target_id)
                    if computer is None or not computer.get("address"):
                        raise RuntimeError("The computer has no saved private connection path.")
                    address = str(computer["address"])
                    if action_type == "probe_connection":
                        result = diagnostics.probe(address, DIAGNOSTIC_AUTHORIZATION)
                    else:
                        result = diagnostics.diagnose(address, DIAGNOSTIC_AUTHORIZATION)
                else:
                    raise RuntimeError(
                        f"Node BoxLink rejected unsupported action type: {action_type}"
                    )
            except Exception as error:
                status = "failed"
                result = {"message": str(error)[:1000]}
            self._post_server_json(
                f"/api/v1/node-sync/{self.node_id}/actions/{action_id}/result",
                {"status": status, "result": result},
            )
            self.store.complete_action(action_id, status)
            completed.append(action_id)
        return completed

    def build_snapshot(
        self,
        status: dict[str, object],
        local_jobs: object,
    ) -> dict[str, object]:
        now = utc_now()
        raw_links: object = (
            load_computers(str(self.state_directory))
            if self.state_directory is not None
            else status.get("managed_computers", status.get("target_links", []))
        )
        links = raw_links if isinstance(raw_links, list) else []
        computers: list[dict[str, object]] = []
        connections: list[dict[str, object]] = []
        address_to_id: dict[str, str] = {}
        for link in links:
            if not isinstance(link, dict):
                continue
            hostname = str(link.get("hostname") or "Managed computer")
            target_id = str(link.get("target_id") or self.store.target_id(hostname))
            address = str(link.get("address") or "")
            if address:
                address_to_id[address] = target_id
            connected = str(link.get("status", "offline")).lower() in {
                "online",
                "connected",
                "available",
            }
            raw_connections = link.get("connections", [])
            connection_types = {
                str(value.get("connection_type"))
                for value in raw_connections
                if isinstance(value, dict)
            } if isinstance(raw_connections, list) else set()
            capabilities = ["managed-diagnostics"]
            if connection_types.intersection({"ssh", "boxlink-ssh"}):
                capabilities.append("ssh")
            if "winrm" in connection_types:
                capabilities.append("winrm")
            if "rdp" in connection_types:
                capabilities.append("remote-desktop")
            if "outbound-boxlink" in connection_types:
                capabilities.append("direct-boxlink")
            computers.append(
                {
                    "id": target_id,
                    "node_id": self.node_id,
                    "friendly_name": str(link.get("friendly_name") or hostname),
                    "kind": str(link.get("platform") or "computer").lower(),
                    "status": "online" if connected else "offline",
                    "capabilities": capabilities,
                    "last_seen_at": link.get("last_checked"),
                    "updated_at": now,
                }
            )
            if isinstance(raw_connections, list) and raw_connections:
                for priority, connection in enumerate(raw_connections, start=40):
                    if not isinstance(connection, dict):
                        continue
                    raw_status = str(connection.get("status", "unknown"))
                    raw_connection_id = str(connection.get("id") or priority)
                    connection_id = (
                        raw_connection_id
                        if raw_connection_id.startswith(f"{target_id}-")
                        else f"{target_id}-{raw_connection_id}"
                    )
                    connections.append(
                        {
                            "id": connection_id,
                            "node_id": self.node_id,
                            "computer_id": target_id,
                            "friendly_name": str(connection.get("friendly_name") or "Connection"),
                            "connection_type": str(connection.get("connection_type") or "other"),
                            "description": str(connection.get("description") or "Saved connection method"),
                            "status": raw_status if raw_status in {"available", "unavailable", "degraded", "unknown"} else "unavailable" if raw_status == "setup-required" else "available" if raw_status == "connected" else "unknown",
                            "priority": priority,
                            "scope": "remote" if connection.get("connection_type") == "outbound-boxlink" else "local",
                            "details": {
                                "address": connection.get("address"),
                                "transport": connection.get("transport"),
                                "interface": connection.get("interface"),
                                "setup_required": raw_status == "setup-required",
                            },
                            "last_seen_at": connection.get("last_seen_at"),
                            "updated_at": now,
                        }
                    )
            else:
                connections.append(
                    {
                        "id": f"{target_id}-SSH",
                        "node_id": self.node_id,
                        "computer_id": target_id,
                        "friendly_name": "Managed Link",
                        "connection_type": "ssh",
                        "description": "Authorized managed connection",
                        "status": "available" if connected else "unavailable",
                        "priority": 40,
                        "scope": "any",
                        "details": {"address": address or None, "transport": link.get("transport"), "interface": link.get("interface")},
                        "last_seen_at": link.get("last_checked"),
                        "updated_at": now,
                    }
                )
        default_route = None
        network = status.get("network")
        if isinstance(network, dict):
            default_route = network.get("default_route")
        node_connections = [
            {
                "id": f"{self.node_id}-BOXLINK",
                "node_id": self.node_id,
                "friendly_name": "BoxLink",
                "connection_type": "boxlink",
                "description": "Secure outbound server path",
                "status": "available",
                "priority": 10,
                "scope": "remote",
                "details": {"server": self.server_url, "protocol": "https"},
                "updated_at": now,
            },
            {
                "id": f"{self.node_id}-LOCAL",
                "node_id": self.node_id,
                "friendly_name": "Local",
                "connection_type": "local-network",
                "description": "Local network connection",
                "status": "available",
                "priority": 20,
                "scope": "local",
                "details": {"route": default_route},
                "updated_at": now,
            },
            {
                "id": f"{self.node_id}-BBPI4",
                "node_id": self.node_id,
                "friendly_name": "BBPI4",
                "connection_type": "pi-desktop",
                "description": "Private Pi Desktop",
                "status": "available",
                "priority": 30,
                "scope": "local",
                "details": {
                    "hostname": status.get("hostname"),
                    "viewer_port": 8790,
                    "tunnel_port": 6080,
                    "protocol": "vnc-over-ssh",
                },
                "updated_at": now,
            },
        ]
        jobs: list[dict[str, object]] = []
        if isinstance(local_jobs, list):
            for item in local_jobs:
                if not isinstance(item, dict) or not item.get("id"):
                    continue
                raw_status = str(item.get("status", "queued")).lower()
                job_status = raw_status if raw_status in {
                    "queued", "running", "paused", "succeeded", "failed", "cancelled"
                } else "succeeded" if raw_status == "completed" else "failed"
                target = str(item.get("target") or "")
                created = item.get("created_at") or now
                updated = item.get("finished_at") or item.get("started_at") or created
                jobs.append(
                    {
                        "id": f"BB-JOB-{str(item['id']).upper()}",
                        "node_id": self.node_id,
                        "computer_id": address_to_id.get(target),
                        "title": f"{item.get('profile', 'BoxBrain')} assessment",
                        "status": job_status,
                        "progress": 100 if job_status == "succeeded" else 0,
                        "summary": item.get("error"),
                        "created_at": created,
                        "updated_at": updated,
                    }
                )
        revision = int(time.time())
        return {
            "node": {
                "id": self.node_id,
                "friendly_name": self.node_name,
                "status": "online",
                "server_connection_state": "syncing",
                "local_state_revision": revision,
                "queued_event_count": len(self.store.pending_events()),
                "capabilities": ["local-first", "outbound-sync", "managed-computers"],
                "last_seen_at": now,
                "updated_at": now,
            },
            "computers": computers,
            "connections": [*node_connections, *connections],
            "jobs": jobs,
            "events": self.store.pending_events(),
        }

    def _get_local_json(self, path: str) -> dict[str, object]:
        request = Request(f"{self.local_api_url}{path}", method="GET")
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                payload = json.load(response)
        except (HTTPError, URLError, OSError, json.JSONDecodeError) as error:
            raise SyncTransportError(f"Local BoxBrain API request failed: {error}") from error
        if not isinstance(payload, dict):
            raise SyncTransportError("Local BoxBrain API returned invalid data.")
        return payload

    def _post_server_json(
        self, path: str, payload: dict[str, object]
    ) -> dict[str, object]:
        request = Request(
            f"{self.server_url}{path}",
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-BoxBrain-Node-Token": self.node_token,
                "User-Agent": "BoxBrain-Node-Sync/1",
            },
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                result = json.load(response)
        except (HTTPError, URLError, OSError, json.JSONDecodeError) as error:
            raise SyncTransportError(f"Central BoxBrain sync failed: {error}") from error
        if not isinstance(result, dict):
            raise SyncTransportError("Central BoxBrain server returned invalid data.")
        return result


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("BOXBRAIN_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    state_dir = Path(os.environ.get("BOXBRAIN_STATE_DIR", "/var/lib/boxbrain"))
    interval = max(2, int(os.environ.get("BOXBRAIN_SYNC_INTERVAL", "5")))
    server_url = os.environ.get(
        "BOXBRAIN_SERVER_URL", "https://boxbrain.arkmatx.com"
    )
    token = os.environ.get("BOXBRAIN_NODE_SYNC_TOKEN", "")
    if not token:
        LOG.warning("BOXBRAIN_NODE_SYNC_TOKEN is not configured; sync is idle.")
        while True:
            time.sleep(60)
    store = SyncStore(state_dir / "sync.sqlite3")
    client = BoxBrainSyncClient(
        server_url=server_url,
        node_token=token,
        node_id=os.environ.get("BOXBRAIN_NODE_ID", "BB-NODE-001"),
        node_name=os.environ.get("BOXBRAIN_NODE_NAME", "BoxBrain Pi4"),
        local_api_url=os.environ.get(
            "BOXBRAIN_LOCAL_API_URL", "http://127.0.0.1:8787"
        ),
        store=store,
        state_directory=state_dir,
    )
    store.enqueue_event(
        event_type="node.sync_started",
        source_type="node",
        source_id=client.node_id,
        message="Outbound BoxLink synchronization started.",
        details={"hostname": socket.gethostname()},
    )
    while True:
        try:
            client.run_once()
            client.execute_pending_actions(state_dir)
        except SyncTransportError as error:
            LOG.warning("%s", error)
        except Exception:
            LOG.exception("Unexpected BoxBrain sync failure")
        time.sleep(interval)


if __name__ == "__main__":
    main()
