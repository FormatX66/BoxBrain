#!/usr/bin/env python3
import sqlite3, json, hashlib, time, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "slush.db"

class AurumHive:
    def __init__(self, node_name, capabilities):
        self.node_name = node_name
        self.capabilities = capabilities
        self.node_id = hashlib.sha256(node_name.encode()).hexdigest()[:16]
        self.db = sqlite3.connect(DB)
        self.db.execute("PRAGMA journal_mode=WAL")
        self._schema()
        self._register()

    def _schema(self):
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS hive_nodes (
            node_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            capabilities TEXT NOT NULL,
            last_seen INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS hive_events (
            event_id TEXT PRIMARY KEY,
            origin_node TEXT NOT NULL,
            event_type TEXT NOT NULL,
            object_id BLOB,
            payload BLOB NOT NULL,
            created INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS hive_receipts (
            node_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            status TEXT NOT NULL,
            processed INTEGER NOT NULL,
            PRIMARY KEY (node_id, event_id)
        );
        """)
        self.db.commit()

    def _register(self):
        self.db.execute("""
            INSERT INTO hive_nodes(node_id,name,capabilities,last_seen)
            VALUES(?,?,?,?)
            ON CONFLICT(node_id) DO UPDATE SET
              capabilities=excluded.capabilities,
              last_seen=excluded.last_seen
        """, (self.node_id, self.node_name, json.dumps(self.capabilities), int(time.time())))
        self.db.commit()

    def publish_delta(self, payload, object_id=None):
        eid = uuid.uuid4().hex
        self.db.execute("""
            INSERT INTO hive_events(event_id,origin_node,event_type,object_id,payload,created)
            VALUES(?,?,?,?,?,?)
        """, (
            eid, self.node_id, "state_delta", object_id,
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
            int(time.time())
        ))
        self.db.commit()
        return eid

    def receive(self):
        rows = self.db.execute("""
            SELECT e.event_id,e.origin_node,e.event_type,e.object_id,e.payload,e.created
            FROM hive_events e
            LEFT JOIN hive_receipts r
              ON r.event_id=e.event_id AND r.node_id=?
            WHERE r.event_id IS NULL AND e.origin_node<>?
            ORDER BY e.created ASC
        """, (self.node_id, self.node_id)).fetchall()

        wakes = []
        for eid, origin, etype, object_id, payload, created in rows:
            data = json.loads(payload)
            compatible = (
                etype == "state_delta"
                and data.get("merge_policy", {}).get("require_provenance", True)
            )
            status = "merged" if compatible else "rejected"
            self.db.execute("""
                INSERT OR REPLACE INTO hive_receipts(node_id,event_id,status,processed)
                VALUES(?,?,?,?)
            """, (self.node_id, eid, status, int(time.time())))
            if compatible:
                wakes.append({
                    "event_id": eid,
                    "origin": origin,
                    "action": "wake_bounded_cycle",
                    "payload": data
                })
        self.db.commit()
        return wakes

if __name__ == "__main__":
    hive = AurumHive("Aurum-Local", ["slush", "python", "worker"])
    for wake in hive.receive():
        print(json.dumps(wake, indent=2))
