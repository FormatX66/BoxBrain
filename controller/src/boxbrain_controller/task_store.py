from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from uuid import UUID, uuid4

from .models import AuditEvent, TaskCreate, TaskRecord, TaskStatus


class TaskStore:
    """SQLite-backed task queue with an append-only audit event table."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self._lock = Lock()
        self._initialize()

    def create(self, request: TaskCreate) -> TaskRecord:
        created_at = datetime.now(UTC)
        record = TaskRecord(
            id=uuid4(),
            goal=request.goal,
            target_id=request.target_id,
            policy_profile=request.policy_profile,
            status=TaskStatus.QUEUED,
            created_at=created_at,
        )
        event_id = uuid4()
        details = json.dumps(
            {
                "goal": record.goal,
                "policy_profile": record.policy_profile,
                "status": record.status,
            },
            separators=(",", ":"),
        )
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks (
                    id, goal, target_id, policy_profile, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(record.id),
                    record.goal,
                    record.target_id,
                    record.policy_profile,
                    record.status,
                    record.created_at.isoformat(),
                ),
            )
            connection.execute(
                """
                INSERT INTO audit_events (
                    id, event_type, task_id, target_id, message, details_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event_id),
                    "task.queued",
                    str(record.id),
                    record.target_id,
                    "Task queued; executor remains disabled.",
                    details,
                    created_at.isoformat(),
                ),
            )
        return record

    def list(self) -> list[TaskRecord]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, goal, target_id, policy_profile, status, created_at
                FROM tasks
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [self._task_from_row(row) for row in rows]

    def get(self, task_id: UUID) -> TaskRecord | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, goal, target_id, policy_profile, status, created_at
                FROM tasks
                WHERE id = ?
                """,
                (str(task_id),),
            ).fetchone()
        return self._task_from_row(row) if row else None

    def list_events(self, *, limit: int = 100) -> list[AuditEvent]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT sequence, id, event_type, task_id, target_id, message,
                       details_json, created_at
                FROM audit_events
                ORDER BY sequence DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._event_from_row(row) for row in rows]

    def _initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    policy_profile TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    task_id TEXT,
                    target_id TEXT,
                    message TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES tasks(id)
                );

                CREATE TRIGGER IF NOT EXISTS audit_events_no_update
                BEFORE UPDATE ON audit_events
                BEGIN
                    SELECT RAISE(ABORT, 'audit events are append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
                BEFORE DELETE ON audit_events
                BEGIN
                    SELECT RAISE(ABORT, 'audit events are append-only');
                END;
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _task_from_row(row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            id=UUID(row["id"]),
            goal=row["goal"],
            target_id=row["target_id"],
            policy_profile=row["policy_profile"],
            status=TaskStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> AuditEvent:
        return AuditEvent(
            sequence=row["sequence"],
            id=UUID(row["id"]),
            event_type=row["event_type"],
            task_id=UUID(row["task_id"]) if row["task_id"] else None,
            target_id=row["target_id"],
            message=row["message"],
            details=json.loads(row["details_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
