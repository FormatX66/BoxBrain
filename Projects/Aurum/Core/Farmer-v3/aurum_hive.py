#!/usr/bin/env python3
"""Aurum Hive durable state exchange with immediate Farmer wake-up."""
from __future__ import annotations

import hashlib
import json
import os
import socket
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get("AURUM_SLUSH_DB", str(ROOT / "slush.db")))
WAKE_SOCKET = Path(os.environ.get("AURUM_FARMER_SOCKET", str(DB.parent / "aurum-farmer.sock")))


class AurumHive:
    def __init__(
        self,
        node_name: str,
        capabilities: list[str],
        db_path: Path | str = DB,
        wake_socket: Path | str = WAKE_SOCKET,
    ) -> None:
        self.node_name = node_name
        self.capabilities = capabilities
        self.node_id = hashlib.sha256(node_name.encode()).hexdigest()[:16]
        self.db_path = Path(db_path)
        self.wake_socket = Path(wake_socket)
        self.db = sqlite3.connect(self.db_path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.last_farmer_ack: dict[str, Any] | None = None
        self._register()

    def _register(self) -> None:
        self.db.execute(
            """
            INSERT INTO hive_nodes(node_id,name,capabilities,last_seen)
            VALUES(?,?,?,?)
            ON CONFLICT(node_id) DO UPDATE SET
              capabilities=excluded.capabilities,
              last_seen=excluded.last_seen
            """,
            (self.node_id, self.node_name, json.dumps(self.capabilities), int(time.time())),
        )
        self.db.commit()

    def _wake_worker(self, event: dict[str, Any]) -> dict[str, Any] | None:
        if not hasattr(socket, "AF_UNIX"):
            return None
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(2.0)
                client.connect(str(self.wake_socket))
                client.sendall(json.dumps(event, sort_keys=True, separators=(",", ":")).encode("utf-8"))
                try:
                    raw = client.recv(4096)
                except socket.timeout:
                    raw = b""
            if raw:
                decoded = json.loads(raw.decode("utf-8"))
                if isinstance(decoded, dict):
                    return decoded
            return {"status": "signaled", "processed": None}
        except (OSError, ValueError, json.JSONDecodeError):
            # State is already durable. The worker drains it on process restart.
            return None

    def publish_delta(self, payload: dict[str, Any], object_id: str | None = None) -> str:
        event_id = uuid.uuid4().hex
        self.db.execute(
            """
            INSERT INTO hive_events(event_id,origin_node,event_type,object_id,payload,created)
            VALUES(?,?,?,?,?,?)
            """,
            (
                event_id,
                self.node_id,
                "state_delta",
                object_id,
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
                int(time.time()),
            ),
        )
        self.db.commit()
        self.last_farmer_ack = self._wake_worker({"event": "hive_delta", "event_id": event_id, "origin": self.node_id})
        return event_id

    def receive(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            """
            SELECT e.event_id,e.origin_node,e.event_type,e.object_id,e.payload,e.created
            FROM hive_events e
            LEFT JOIN hive_receipts r
              ON r.event_id=e.event_id AND r.node_id=?
            WHERE r.event_id IS NULL AND e.origin_node<>?
            ORDER BY e.created ASC
            """,
            (self.node_id, self.node_id),
        ).fetchall()

        wakes: list[dict[str, Any]] = []
        for event_id, origin, event_type, object_id, payload, created in rows:
            data = json.loads(payload)
            compatible = event_type == "state_delta" and data.get("merge_policy", {}).get("require_provenance", True)
            status = "merged" if compatible else "rejected"
            self.db.execute(
                """
                INSERT OR REPLACE INTO hive_receipts(node_id,event_id,status,processed)
                VALUES(?,?,?,?)
                """,
                (self.node_id, event_id, status, int(time.time())),
            )
            if compatible:
                wakes.append(
                    {
                        "event_id": event_id,
                        "origin": origin,
                        "action": "wake_bounded_cycle",
                        "payload": data,
                    }
                )
        self.db.commit()
        if wakes:
            self.last_farmer_ack = self._wake_worker({"event": "hive_receive", "event_ids": [wake["event_id"] for wake in wakes]})
        return wakes

    def close(self) -> None:
        self.db.close()


if __name__ == "__main__":
    hive = AurumHive("Aurum-Local", ["slush", "python", "worker", "farmer-wake"])
    try:
        for wake in hive.receive():
            print(json.dumps(wake, indent=2))
    finally:
        hive.close()
