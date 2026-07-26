"""SQLite persistence for BoxBrain assessments and findings."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any
import uuid


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    target TEXT NOT NULL,
    profile TEXT NOT NULL,
    authorization_digest TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    error TEXT,
    report_json TEXT,
    report_html TEXT
);

CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    ip_address TEXT NOT NULL,
    hostname TEXT,
    mac_address TEXT,
    vendor TEXT,
    state TEXT NOT NULL,
    UNIQUE(job_id, ip_address)
);

CREATE TABLE IF NOT EXISTS services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    port INTEGER NOT NULL,
    protocol TEXT NOT NULL,
    state TEXT NOT NULL,
    name TEXT,
    product TEXT,
    version TEXT,
    UNIQUE(job_id, asset_id, port, protocol)
);

CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    asset_id INTEGER REFERENCES assets(id) ON DELETE CASCADE,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT NOT NULL,
    recommendation TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_assets_job_id ON assets(job_id);
CREATE INDEX IF NOT EXISTS idx_services_job_id ON services(job_id);
CREATE INDEX IF NOT EXISTS idx_findings_job_id ON findings(job_id);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Storage:
    def __init__(self, state_directory: str) -> None:
        self.state_directory = Path(state_directory)
        self.database_path = self.state_directory / "boxbrain.db"
        self.report_directory = self.state_directory / "reports"

    def initialize(self) -> None:
        self.state_directory.mkdir(parents=True, exist_ok=True)
        self.report_directory.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def _connection(self) -> Any:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def create_job(self, target: str, profile: str, authorization: str) -> str:
        job_id = uuid.uuid4().hex[:16]
        digest = hashlib.sha256(authorization.encode("utf-8")).hexdigest()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    id, target, profile, authorization_digest, status, created_at
                ) VALUES (?, ?, ?, ?, 'queued', ?)
                """,
                (job_id, target, profile, digest, utc_now()),
            )
        return job_id

    def update_job(self, job_id: str, **values: Any) -> None:
        allowed = {
            "status",
            "started_at",
            "finished_at",
            "error",
            "report_json",
            "report_html",
        }
        updates = {key: value for key, value in values.items() if key in allowed}
        if not updates:
            return
        clause = ", ".join(f"{key} = ?" for key in updates)
        with self._connection() as connection:
            connection.execute(
                f"UPDATE jobs SET {clause} WHERE id = ?",
                (*updates.values(), job_id),
            )

    def save_asset(
        self,
        job_id: str,
        ip_address: str,
        hostname: str | None,
        mac_address: str | None,
        vendor: str | None,
        state: str = "up",
    ) -> int:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO assets (
                    job_id, ip_address, hostname, mac_address, vendor, state
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id, ip_address) DO UPDATE SET
                    hostname = excluded.hostname,
                    mac_address = excluded.mac_address,
                    vendor = excluded.vendor,
                    state = excluded.state
                """,
                (job_id, ip_address, hostname, mac_address, vendor, state),
            )
            row = connection.execute(
                "SELECT id FROM assets WHERE job_id = ? AND ip_address = ?",
                (job_id, ip_address),
            ).fetchone()
        if row is None:
            raise RuntimeError("Asset could not be saved.")
        return int(row["id"])

    def save_service(
        self,
        job_id: str,
        asset_id: int,
        port: int,
        protocol: str,
        state: str,
        name: str | None,
        product: str | None,
        version: str | None,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO services (
                    job_id, asset_id, port, protocol, state, name, product, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (job_id, asset_id, port, protocol, state, name, product, version),
            )

    def save_finding(
        self,
        job_id: str,
        asset_id: int | None,
        severity: str,
        title: str,
        detail: str,
        recommendation: str,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO findings (
                    job_id, asset_id, severity, title, detail, recommendation
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, asset_id, severity, title, detail, recommendation),
            )

    def list_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    jobs.*,
                    (SELECT COUNT(*) FROM assets WHERE assets.job_id = jobs.id) AS asset_count,
                    (SELECT COUNT(*) FROM services WHERE services.job_id = jobs.id) AS service_count,
                    (SELECT COUNT(*) FROM findings WHERE findings.job_id = jobs.id) AS finding_count
                FROM jobs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        jobs = [job for job in self.list_jobs(100) if job["id"] == job_id]
        return jobs[0] if jobs else None

    def latest_summary(self) -> dict[str, Any] | None:
        jobs = self.list_jobs(1)
        return jobs[0] if jobs else None

    def build_report(self, job_id: str) -> dict[str, Any]:
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        with self._connection() as connection:
            asset_rows = connection.execute(
                "SELECT * FROM assets WHERE job_id = ? ORDER BY ip_address",
                (job_id,),
            ).fetchall()
            service_rows = connection.execute(
                """
                SELECT services.*, assets.ip_address
                FROM services
                JOIN assets ON assets.id = services.asset_id
                WHERE services.job_id = ?
                ORDER BY assets.ip_address, services.port
                """,
                (job_id,),
            ).fetchall()
            finding_rows = connection.execute(
                """
                SELECT findings.*, assets.ip_address
                FROM findings
                LEFT JOIN assets ON assets.id = findings.asset_id
                WHERE findings.job_id = ?
                ORDER BY
                    CASE severity
                        WHEN 'critical' THEN 1
                        WHEN 'high' THEN 2
                        WHEN 'medium' THEN 3
                        WHEN 'low' THEN 4
                        ELSE 5
                    END,
                    findings.id
                """,
                (job_id,),
            ).fetchall()

        return {
            "schema_version": 1,
            "generated_at": utc_now(),
            "job": job,
            "assets": [dict(row) for row in asset_rows],
            "services": [dict(row) for row in service_rows],
            "findings": [dict(row) for row in finding_rows],
        }

    def write_report(self, job_id: str, html: str) -> tuple[str, str]:
        report = self.build_report(job_id)
        json_path = self.report_directory / f"{job_id}.json"
        html_path = self.report_directory / f"{job_id}.html"
        json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        html_path.write_text(html, encoding="utf-8")
        self.update_job(
            job_id,
            report_json=str(json_path),
            report_html=str(html_path),
        )
        return str(json_path), str(html_path)
