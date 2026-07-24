from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from uuid import UUID, uuid4

from .models import (
    AuditEvent,
    AuditEventType,
    EmergencyStopState,
    TaskCreate,
    TaskRecord,
    TaskStatus,
)


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

    def append_event(
        self,
        *,
        event_type: AuditEventType,
        target_id: str | None,
        message: str,
        details: dict[str, object],
        task_id: UUID | None = None,
    ) -> AuditEvent:
        event_id = uuid4()
        created_at = datetime.now(UTC)
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO audit_events (
                    id, event_type, task_id, target_id, message, details_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event_id),
                    event_type,
                    str(task_id) if task_id else None,
                    target_id,
                    message,
                    json.dumps(details, separators=(",", ":")),
                    created_at.isoformat(),
                ),
            )
            sequence = cursor.lastrowid
        if sequence is None:
            raise RuntimeError("SQLite did not assign an audit sequence.")
        return AuditEvent(
            sequence=sequence,
            id=event_id,
            event_type=event_type,
            task_id=task_id,
            target_id=target_id,
            message=message,
            details=details,
            created_at=created_at,
        )

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

    def get_emergency_stop(self) -> EmergencyStopState:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT engaged, reason, generation, changed_at
                FROM controller_state
                WHERE key = 'emergency_stop'
                """
            ).fetchone()
        if row is None:
            raise RuntimeError("Emergency-stop state is not initialized.")
        return self._emergency_stop_from_row(row)

    def engage_emergency_stop(self, *, reason: str) -> EmergencyStopState:
        created_at = datetime.now(UTC)
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT engaged, reason, generation, changed_at
                FROM controller_state
                WHERE key = 'emergency_stop'
                """
            ).fetchone()
            if row is None:
                raise RuntimeError("Emergency-stop state is not initialized.")

            changed = not bool(row["engaged"])
            if changed:
                generation = row["generation"] + 1
                connection.execute(
                    """
                    UPDATE controller_state
                    SET engaged = 1, reason = ?, generation = ?, changed_at = ?
                    WHERE key = 'emergency_stop'
                    """,
                    (reason, generation, created_at.isoformat()),
                )
                state = EmergencyStopState(
                    engaged=True,
                    reason=reason,
                    generation=generation,
                    changed_at=created_at,
                )
            else:
                state = self._emergency_stop_from_row(row)

            self._insert_event(
                connection,
                event_type="safety.emergency_stop_engaged",
                target_id=None,
                message=(
                    "Emergency stop engaged."
                    if changed
                    else "Emergency stop engagement requested; already engaged."
                ),
                details={
                    "result": "engaged" if changed else "already_engaged",
                    "reason": state.reason,
                    "generation": state.generation,
                },
                created_at=created_at,
            )
        return state

    def reset_emergency_stop(self) -> EmergencyStopState:
        created_at = datetime.now(UTC)
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT engaged, reason, generation, changed_at
                FROM controller_state
                WHERE key = 'emergency_stop'
                """
            ).fetchone()
            if row is None:
                raise RuntimeError("Emergency-stop state is not initialized.")

            changed = bool(row["engaged"])
            prior_reason = row["reason"]
            if changed:
                generation = row["generation"] + 1
                connection.execute(
                    """
                    UPDATE controller_state
                    SET engaged = 0, reason = NULL, generation = ?, changed_at = ?
                    WHERE key = 'emergency_stop'
                    """,
                    (generation, created_at.isoformat()),
                )
                state = EmergencyStopState(
                    engaged=False,
                    reason=None,
                    generation=generation,
                    changed_at=created_at,
                )
            else:
                state = self._emergency_stop_from_row(row)

            self._insert_event(
                connection,
                event_type="safety.emergency_stop_reset",
                target_id=None,
                message=(
                    "Emergency stop reset."
                    if changed
                    else "Emergency stop reset requested; already clear."
                ),
                details={
                    "result": "reset" if changed else "already_clear",
                    "prior_reason": prior_reason,
                    "generation": state.generation,
                },
                created_at=created_at,
            )
        return state

    def _initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        initialized_at = datetime.now(UTC).isoformat()
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

                CREATE TABLE IF NOT EXISTS controller_state (
                    key TEXT PRIMARY KEY CHECK (key = 'emergency_stop'),
                    engaged INTEGER NOT NULL CHECK (engaged IN (0, 1)),
                    reason TEXT,
                    generation INTEGER NOT NULL CHECK (generation >= 0),
                    changed_at TEXT NOT NULL
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
            connection.execute(
                """
                INSERT OR IGNORE INTO controller_state (
                    key, engaged, reason, generation, changed_at
                ) VALUES ('emergency_stop', 0, NULL, 0, ?)
                """,
                (initialized_at,),
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

    @staticmethod
    def _emergency_stop_from_row(row: sqlite3.Row) -> EmergencyStopState:
        return EmergencyStopState(
            engaged=bool(row["engaged"]),
            reason=row["reason"],
            generation=row["generation"],
            changed_at=datetime.fromisoformat(row["changed_at"]),
        )

    @staticmethod
    def _insert_event(
        connection: sqlite3.Connection,
        *,
        event_type: AuditEventType,
        target_id: str | None,
        message: str,
        details: dict[str, object],
        created_at: datetime,
        task_id: UUID | None = None,
    ) -> int:
        cursor = connection.execute(
            """
            INSERT INTO audit_events (
                id, event_type, task_id, target_id, message, details_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                event_type,
                str(task_id) if task_id else None,
                target_id,
                message,
                json.dumps(details, separators=(",", ":")),
                created_at.isoformat(),
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not assign an audit sequence.")
        return cursor.lastrowid
