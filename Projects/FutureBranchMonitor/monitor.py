"""Local, read-only Future Branch monitor and explicit public decision journal."""
import argparse
from contextlib import closing
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import threading
import time
from urllib.error import HTTPError
from urllib.request import build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parent
SCHEMA = "aurum.future-branch.chat-check.v1"
PHASES = {"planned", "checking", "executing", "checked", "failed", "waiting"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def string(value, limit=500):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError("missing or oversized text")
    return value.strip()


def strings(value, limit=12):
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError("invalid list")
    return [string(v) for v in value]


class Journal:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS reports (
                    sequence INTEGER PRIMARY KEY, digest TEXT UNIQUE NOT NULL,
                    thread_id TEXT NOT NULL, received_at REAL NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS snapshots (
                    name TEXT PRIMARY KEY, observed_at REAL NOT NULL, body TEXT NOT NULL);
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def record(self, item):
        if item.get("schema") != SCHEMA or item.get("phase") not in PHASES:
            raise ValueError("invalid decision report schema or phase")
        report = {"schema": SCHEMA, "thread_id": string(item.get("thread_id"), 100),
                  "operation_id": string(item.get("operation_id"), 160), "phase": item["phase"],
                  "summary": string(item.get("summary")), "candidates": strings(item.get("candidates")),
                  "selected": string(item.get("selected")), "evidence": strings(item.get("evidence")),
                  "recovery": string(item.get("recovery")), "source": "self_reported"}
        if len(report["candidates"]) < 2 or report["selected"] not in report["candidates"]:
            raise ValueError("include at least two public action choices and select one")
        body = canonical(report)
        key = hashlib.sha256(body.encode()).hexdigest()
        with closing(self.connect()) as db, db:
            cursor = db.execute("INSERT OR IGNORE INTO reports(digest,thread_id,received_at,body) VALUES(?,?,?,?)",
                                (key, report["thread_id"], time.time(), body))
            return {"recorded": bool(cursor.rowcount), "digest": key}

    def snapshot(self, name, body):
        with closing(self.connect()) as db, db:
            db.execute("INSERT OR REPLACE INTO snapshots VALUES(?,?,?)", (name, time.time(), canonical(body)))

    def context(self, item):
        tasks = item.get("tasks")
        if not isinstance(tasks, list) or len(tasks) > 200:
            raise ValueError("invalid task snapshot")
        safe = [{"id": string(t.get("id"), 100), "title": string(t.get("title"), 5000),
                 "status": string(t.get("status"), 40), "kind": string(t.get("kind", "unknown"), 40)} for t in tasks]
        self.snapshot("tasks", {"tasks": safe, "scope": "Most recent tasks returned by the app; not every account or device"})

    def read(self, now=None):
        now = time.time() if now is None else now
        with closing(self.connect()) as db:
            snapshots = {r["name"]: {"observed_at": r["observed_at"], "age_seconds": max(0, now-r["observed_at"]),
                                     **json.loads(r["body"])} for r in db.execute("SELECT * FROM snapshots")}
            reports = [{**json.loads(r["body"]), "received_at": r["received_at"], "sequence": r["sequence"],
                        "age_seconds": max(0, now-r["received_at"])} for r in db.execute(
                            "SELECT * FROM reports ORDER BY sequence DESC LIMIT 100")]
            latest = {r["thread_id"]: {**json.loads(r["body"]), "age_seconds": max(0, now-r["received_at"])}
                      for r in db.execute("SELECT * FROM reports WHERE sequence IN (SELECT MAX(sequence) FROM reports GROUP BY thread_id)")}
        tasks = snapshots.get("tasks", {})
        coverage = []
        for task in tasks.get("tasks", []):
            if task["status"] != "active":
                continue
            report = latest.get(task["id"])
            coverage.append({**task, "coverage": "unobserved" if report is None else (
                "stale_report" if report["age_seconds"] > 1800 else "reported"),
                "latest_report": report})
        engine = snapshots.get("engine", {})
        engine["stale"] = not engine or engine.get("age_seconds", 999) > 15
        return {"schema": "aurum.future-branch.dashboard.v1", "observed_at": now, "engine": engine,
                "task_inventory": {"observed_at": tasks.get("observed_at"), "age_seconds": tasks.get("age_seconds"),
                                   "stale": not tasks or tasks.get("age_seconds", 999) > 600,
                                   "scope": tasks.get("scope", "No task inventory received")},
                "coverage": coverage, "chat_reports": reports,
                "limits": "Chat reports summarize actions and evidence; they do not expose private reasoning or prove independent verification."}


def sample_engine(journal):
    # No proxy, credentials, configurable destinations, or arbitrary network access.
    opener = build_opener(ProxyHandler({}))
    try:
        detailed = True
        try:
            response = opener.open("http://127.0.0.1:19466/monitor", timeout=2)
        except HTTPError as error:
            if error.code not in (401, 404):
                raise
            detailed = False
            response = opener.open("http://127.0.0.1:19466/health", timeout=2)
        with response:
            raw = json.loads(response.read(1_000_000))
        if detailed and raw.get("schema") != "aurum.future-branch.monitor.v1":
            raise ValueError("unexpected monitor schema")
        # Whitelist fields: the health fallback also contains private local paths.
        safe = {key: raw[key] for key in ("status", "activity", "event_chain_valid", "running_attempts",
                "future_branch", "recent_decisions", "job_states", "continuous_exploration") if key in raw}
        safe["activity"] = safe.get("activity", "executing" if safe.get("running_attempts") else "idle")
        journal.snapshot("engine", {"reachable": True, "detailed": detailed, **safe})
    except Exception as error:
        # Do not preserve stale success as current health, nor publish exception contents.
        journal.snapshot("engine", {"reachable": False, "detailed": False, "error": type(error).__name__})


def serve(journal, port=19467):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get("Host") not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
                self.send_error(403)
                return
            if self.path == "/":
                content, mime = (ROOT / "index.html").read_bytes(), "text/html; charset=utf-8"
            elif self.path == "/api/status":
                content, mime = canonical(journal.read()).encode(), "application/json; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *args):
            pass

    stop = threading.Event()

    def poll():
        while not stop.is_set():
            sample_engine(journal)
            stop.wait(5)

    thread = threading.Thread(target=poll, daemon=True)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread.start()
    try:
        server.serve_forever()
    finally:
        stop.set()
        server.server_close()
        thread.join(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data" / "monitor.sqlite3")
    parser.add_argument("command", choices=["serve", "record", "context", "bus", "status", "sample"])
    parser.add_argument("--file", type=Path, help="JSON file for record, context, or bus")
    args = parser.parse_args()
    journal = Journal(args.data)
    if args.command == "serve":
        serve(journal)
        return
    if args.command in {"record", "context", "bus"}:
        if not args.file or args.file.stat().st_size > 2_000_000:
            parser.error("a JSON file smaller than 2 MB is required")
        body = json.loads(args.file.read_text(encoding="utf-8-sig"))
        if args.command == "record":
            print(canonical(journal.record(body)))
        elif args.command == "context":
            journal.context(body)
        else:
            count = 0
            for event in body.get("events", [])[:500]:
                payload = event.get("payload", {})
                if payload.get("schema") == SCHEMA:
                    try:
                        count += int(journal.record(payload)["recorded"])
                    except ValueError:
                        pass
            print(canonical({"imported": count}))
    elif args.command == "sample":
        sample_engine(journal)
        print(canonical(journal.read()))
    else:
        print(canonical(journal.read()))


if __name__ == "__main__":
    main()
