#!/usr/bin/env python3
"""Compact portable Aurum hive node.

Transport-agnostic: peers drop JSON deltas into inbox/; this node validates,
merges and checkpoints them into local Slush. Outbound deltas are written to outbox/.
"""

from __future__ import annotations
import argparse, hashlib, json, sqlite3, time, uuid
from pathlib import Path
from typing import Any

class AurumNode:
    def __init__(self, root: Path, name: str):
        self.root=Path(root).resolve()
        self.name=name
        self.root.mkdir(parents=True,exist_ok=True)
        self.inbox=self.root/"inbox"; self.outbox=self.root/"outbox"
        self.inbox.mkdir(exist_ok=True); self.outbox.mkdir(exist_ok=True)
        self.db_path=self.root/"slush.db"
        self._init_db()

    def _db(self):
        con=sqlite3.connect(self.db_path)
        con.row_factory=sqlite3.Row
        return con

    def _init_db(self):
        with self._db() as con:
            con.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS objects(
              id BLOB PRIMARY KEY, kind TEXT NOT NULL, payload BLOB NOT NULL,
              created INTEGER NOT NULL, updated INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS events(
              event_id TEXT PRIMARY KEY, origin TEXT NOT NULL, payload BLOB NOT NULL,
              status TEXT NOT NULL, created INTEGER NOT NULL, processed INTEGER);
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            """)
            con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('node_name',?)",(self.name,))
            con.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('cycle','0')")

    @staticmethod
    def _pack(value: Any) -> tuple[bytes,bytes]:
        payload=json.dumps(value,sort_keys=True,separators=(",",":")).encode()
        return hashlib.sha256(payload).digest(),payload

    def put(self, kind:str, value:Any) -> str:
        oid,payload=self._pack(value); now=int(time.time())
        with self._db() as con:
            con.execute("""INSERT OR REPLACE INTO objects(id,kind,payload,created,updated)
                           VALUES(?,?,?,?,?)""",(oid,kind,payload,now,now))
        return oid.hex()

    def publish(self, capability:str, payload:dict, reversible:bool=True) -> Path:
        event={
          "schema":1,"event_id":uuid.uuid4().hex,"origin":self.name,
          "capability":capability,"payload":payload,
          "provenance":{"node":self.name,"created":int(time.time())},
          "reversible":bool(reversible)
        }
        p=self.outbox/f'{event["event_id"]}.json'
        p.write_text(json.dumps(event,sort_keys=True,indent=2))
        return p

    def _validate(self,event:dict) -> tuple[bool,str]:
        required={"schema","event_id","origin","capability","payload","provenance","reversible"}
        if set(event)!=required: return False,"schema-fields"
        if event["schema"]!=1: return False,"schema-version"
        if not isinstance(event["event_id"],str) or len(event["event_id"])>64: return False,"event-id"
        if not event.get("provenance",{}).get("node"): return False,"provenance"
        if event["reversible"] is not True: return False,"non-reversible"
        return True,"compatible"

    def ingest(self,event:dict) -> dict:
        ok,reason=self._validate(event); now=int(time.time())
        raw=json.dumps(event,sort_keys=True,separators=(",",":")).encode()
        with self._db() as con:
            prior=con.execute("SELECT status FROM events WHERE event_id=?",(event.get("event_id",""),)).fetchone()
            if prior: return {"status":"duplicate","reason":"already-seen"}
            con.execute("INSERT INTO events(event_id,origin,payload,status,created,processed) VALUES(?,?,?,?,?,?)",
                        (event.get("event_id","invalid"),event.get("origin","unknown"),raw,
                         "merged" if ok else "rejected",now,now))
        if ok:
            self.put("hive_delta",event)
            self.cycle(trigger=event["event_id"])
            return {"status":"merged","reason":reason}
        return {"status":"rejected","reason":reason}

    def process_inbox(self) -> list[dict]:
        results=[]
        for p in sorted(self.inbox.glob("*.json")):
            try:
                event=json.loads(p.read_text())
                result=self.ingest(event)
            except Exception as e:
                result={"status":"error","reason":type(e).__name__}
            results.append({"file":p.name,**result})
            p.rename(p.with_suffix(".done"))
        return results

    def cycle(self, trigger:str="manual") -> dict:
        now=int(time.time())
        with self._db() as con:
            current=int(con.execute("SELECT value FROM meta WHERE key='cycle'").fetchone()[0])
            nxt=current+1
            con.execute("UPDATE meta SET value=? WHERE key='cycle'",(str(nxt),))
        checkpoint={"node":self.name,"cycle":nxt,"trigger":trigger,"time":now}
        self.put("checkpoint",checkpoint)
        return checkpoint

    def status(self) -> dict:
        with self._db() as con:
            cycle=int(con.execute("SELECT value FROM meta WHERE key='cycle'").fetchone()[0])
            objects=con.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
            merged=con.execute("SELECT COUNT(*) FROM events WHERE status='merged'").fetchone()[0]
            rejected=con.execute("SELECT COUNT(*) FROM events WHERE status='rejected'").fetchone()[0]
        return {"node":self.name,"cycle":cycle,"objects":objects,
                "events":{"merged":merged,"rejected":rejected},
                "inbox_pending":len(list(self.inbox.glob("*.json"))),
                "outbox_pending":len(list(self.outbox.glob("*.json")))}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True); p.add_argument("--name",required=True)
    sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("status"); sub.add_parser("cycle"); sub.add_parser("process-inbox")
    pub=sub.add_parser("publish"); pub.add_argument("capability"); pub.add_argument("payload")
    ing=sub.add_parser("ingest"); ing.add_argument("event",nargs="?")
    a=p.parse_args(); n=AurumNode(a.root,a.name)
    if a.cmd=="status": out=n.status()
    elif a.cmd=="cycle": out=n.cycle()
    elif a.cmd=="process-inbox": out=n.process_inbox()
    elif a.cmd=="publish": out={"path":str(n.publish(a.capability,json.loads(a.payload)))}
    else:
        raw=a.event if a.event is not None else sys.stdin.read()
        out=n.ingest(json.loads(raw))
    print(json.dumps(out,indent=2,sort_keys=True))
if __name__=="__main__":
    import sys
    main()
