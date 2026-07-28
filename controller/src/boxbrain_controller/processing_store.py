from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from uuid import UUID, uuid4

from .models import (
    AgentDashboard,
    AgentTaskRecord,
    AgentTaskStatus,
    AgentUsageTotal,
    MemoryKind,
    MemoryRecord,
    ModelProcessingRun,
    ProcessingRun,
    ProjectSummary,
    UsageSummary,
)


_SEARCH_STOPWORDS = {
    "about",
    "and",
    "from",
    "have",
    "into",
    "memory",
    "search",
    "that",
    "the",
    "this",
    "what",
    "with",
}


class ProcessingStore:
    """Durable local workspace for agent runs, memory, tasks, and usage."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self._lock = Lock()
        self._initialize()

    def save(self, *, fingerprint: str, run: ProcessingRun) -> ProcessingRun:
        payload = run.model_dump_json()
        with self._lock, self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO processing_runs (
                        id, fingerprint, source, project, intent, status,
                        run_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(run.id),
                        fingerprint,
                        run.source,
                        run.project,
                        run.intent,
                        run.status,
                        payload,
                        run.created_at.isoformat(),
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO agent_usage_events (
                        run_id, agent_id, status, estimated_tokens, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            str(run.id),
                            step.agent_id,
                            step.status,
                            step.estimated_tokens,
                            run.created_at.isoformat(),
                        )
                        for step in run.steps
                    ],
                )
                self._materialize_run(connection, run)
            except sqlite3.IntegrityError:
                existing = self._get_by_fingerprint(
                    connection,
                    fingerprint=fingerprint,
                )
                if existing is None:
                    raise
                return existing
        return run

    def get(self, run_id: UUID) -> ProcessingRun | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT run_json FROM processing_runs WHERE id = ?",
                (str(run_id),),
            ).fetchone()
        return self._run_from_row(row)

    def get_by_fingerprint(self, fingerprint: str) -> ProcessingRun | None:
        with self._lock, self._connect() as connection:
            return self._get_by_fingerprint(
                connection,
                fingerprint=fingerprint,
            )

    def list(self, *, limit: int = 100) -> list[ProcessingRun]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT run_json
                FROM processing_runs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [ProcessingRun.model_validate(json.loads(row[0])) for row in rows]

    def save_model_run(self, run: ModelProcessingRun) -> ModelProcessingRun:
        payload = run.model_dump_json()
        with self._lock, self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO model_processing_runs (
                        id, local_run_id, model, provider_requests,
                        provider_input_tokens, provider_output_tokens,
                        provider_total_tokens, run_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(run.id),
                        str(run.local_run.id),
                        run.model,
                        run.usage.requests,
                        run.usage.input_tokens,
                        run.usage.output_tokens,
                        run.usage.total_tokens,
                        payload,
                        run.created_at.isoformat(),
                    ),
                )
            except sqlite3.IntegrityError:
                existing = self._get_model_run_for_local(
                    connection,
                    local_run_id=run.local_run.id,
                    model=run.model,
                )
                if existing is None:
                    raise
                return existing
        return run

    def get_model_run(self, run_id: UUID) -> ModelProcessingRun | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT run_json FROM model_processing_runs WHERE id = ?",
                (str(run_id),),
            ).fetchone()
        return self._model_run_from_row(row)

    def get_model_run_for_local(
        self,
        local_run_id: UUID,
        *,
        model: str,
    ) -> ModelProcessingRun | None:
        with self._lock, self._connect() as connection:
            return self._get_model_run_for_local(
                connection,
                local_run_id=local_run_id,
                model=model,
            )

    def list_model_runs(self, *, limit: int = 100) -> list[ModelProcessingRun]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT run_json
                FROM model_processing_runs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            ModelProcessingRun.model_validate(json.loads(row[0]))
            for row in rows
        ]

    def usage_summary(self) -> UsageSummary:
        with self._lock, self._connect() as connection:
            totals = connection.execute(
                """
                SELECT COUNT(*), COALESCE(SUM(estimated_tokens), 0)
                FROM agent_usage_events
                """
            ).fetchone()
            run_count = connection.execute(
                "SELECT COUNT(*) FROM processing_runs"
            ).fetchone()
            provider_totals = connection.execute(
                """
                SELECT COALESCE(SUM(provider_total_tokens), 0)
                FROM model_processing_runs
                """
            ).fetchone()
            rows = connection.execute(
                """
                SELECT agent_id, COUNT(DISTINCT run_id), SUM(estimated_tokens)
                FROM agent_usage_events
                GROUP BY agent_id
                ORDER BY agent_id
                """
            ).fetchall()
        return UsageSummary(
            total_runs=int(run_count[0]) if run_count else 0,
            estimated_tokens=int(totals[1]) if totals else 0,
            provider_tokens_used=(
                int(provider_totals[0]) if provider_totals else 0
            ),
            by_agent=[
                AgentUsageTotal(
                    agent_id=row[0],
                    run_count=int(row[1]),
                    estimated_tokens=int(row[2]),
                )
                for row in rows
            ],
        )

    def list_projects(self) -> list[ProjectSummary]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    p.project_key,
                    p.name,
                    (SELECT COUNT(*) FROM memories AS m
                     WHERE m.project_key = p.project_key),
                    (SELECT COUNT(*) FROM agent_tasks AS t
                     WHERE t.project_key = p.project_key
                       AND t.status = 'open'),
                    p.created_at,
                    p.last_activity_at
                FROM projects AS p
                ORDER BY p.last_activity_at DESC, p.name ASC
                """
            ).fetchall()
        return [self._project_from_row(row) for row in rows]

    def list_memory(
        self,
        *,
        project: str | None = None,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        clauses: list[str] = []
        parameters: list[object] = []
        if project is not None:
            clauses.append("m.project_key = ?")
            parameters.append(_project_key(project))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(limit)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT m.id, m.project_key, p.name, m.kind, m.content,
                       m.source_run_id, m.created_at
                FROM memories AS m
                JOIN projects AS p ON p.project_key = m.project_key
                {where}
                ORDER BY m.created_at DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [self._memory_from_row(row) for row in rows]

    def search_memory(
        self,
        *,
        query: str,
        project: str | None = None,
        limit: int = 20,
    ) -> list[MemoryRecord]:
        terms = _search_terms(query)
        if not terms:
            return []
        clauses = [
            "(" + " OR ".join(
                "LOWER(m.content) LIKE ? ESCAPE '\\'" for _ in terms
            ) + ")"
        ]
        parameters: list[object] = [
            f"%{_escape_like(term.casefold())}%" for term in terms
        ]
        if project is not None:
            clauses.append("m.project_key = ?")
            parameters.append(_project_key(project))
        parameters.append(limit)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT m.id, m.project_key, p.name, m.kind, m.content,
                       m.source_run_id, m.created_at
                FROM memories AS m
                JOIN projects AS p ON p.project_key = m.project_key
                WHERE {' AND '.join(clauses)}
                ORDER BY m.created_at DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [self._memory_from_row(row) for row in rows]

    def list_agent_tasks(
        self,
        *,
        project: str | None = None,
        task_status: AgentTaskStatus | None = None,
        limit: int = 100,
    ) -> list[AgentTaskRecord]:
        clauses: list[str] = []
        parameters: list[object] = []
        if project is not None:
            clauses.append("t.project_key = ?")
            parameters.append(_project_key(project))
        if task_status is not None:
            clauses.append("t.status = ?")
            parameters.append(task_status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(limit)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT t.id, t.project_key, p.name, t.title, t.status,
                       t.source_run_id, t.created_at, t.updated_at
                FROM agent_tasks AS t
                JOIN projects AS p ON p.project_key = t.project_key
                {where}
                ORDER BY t.updated_at DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [self._task_from_row(row) for row in rows]

    def update_agent_task(
        self,
        task_id: UUID,
        *,
        task_status: AgentTaskStatus,
    ) -> AgentTaskRecord | None:
        changed_at = datetime.now(UTC)
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT status FROM agent_tasks WHERE id = ?",
                (str(task_id),),
            ).fetchone()
            if row is None:
                return None
            previous_status = row[0]
            if previous_status != task_status:
                connection.execute(
                    """
                    UPDATE agent_tasks
                    SET status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (task_status, changed_at.isoformat(), str(task_id)),
                )
                connection.execute(
                    """
                    INSERT INTO agent_task_events (
                        task_id, previous_status, new_status, created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        str(task_id),
                        previous_status,
                        task_status,
                        changed_at.isoformat(),
                    ),
                )
            updated = self._get_task_row(connection, task_id)
        return self._task_from_row(updated) if updated else None

    def dashboard(self) -> AgentDashboard:
        projects = self.list_projects()
        usage = self.usage_summary()
        recent_tasks = self.list_agent_tasks(limit=10)
        with self._lock, self._connect() as connection:
            completed = connection.execute(
                "SELECT COUNT(*) FROM agent_tasks WHERE status = 'done'"
            ).fetchone()
        return AgentDashboard(
            project_count=len(projects),
            memory_count=sum(project.memory_count for project in projects),
            open_task_count=sum(
                project.open_task_count for project in projects
            ),
            completed_task_count=int(completed[0]) if completed else 0,
            processing_run_count=usage.total_runs,
            estimated_tokens=usage.estimated_tokens,
            provider_tokens_used=usage.provider_tokens_used,
            projects=projects,
            recent_tasks=recent_tasks,
        )

    def _materialize_run(
        self,
        connection: sqlite3.Connection,
        run: ProcessingRun,
    ) -> None:
        project_key = _project_key(run.project)
        timestamp = run.created_at.isoformat()
        connection.execute(
            """
            INSERT INTO projects (
                project_key, name, created_at, last_activity_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(project_key) DO UPDATE SET
                last_activity_at = excluded.last_activity_at
            """,
            (project_key, run.project, timestamp, timestamp),
        )
        for artifact in run.artifacts:
            if artifact.kind == "memory_note":
                summary = artifact.data.get("summary")
                if isinstance(summary, str):
                    self._insert_memory(
                        connection,
                        run=run,
                        project_key=project_key,
                        kind="summary",
                        content=summary,
                    )
                decisions = artifact.data.get("decisions")
                if isinstance(decisions, list):
                    for decision in decisions:
                        if isinstance(decision, str):
                            self._insert_memory(
                                connection,
                                run=run,
                                project_key=project_key,
                                kind="decision",
                                content=decision,
                            )
            elif artifact.kind == "task":
                items = artifact.data.get("items")
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, str):
                            self._insert_task(
                                connection,
                                run=run,
                                project_key=project_key,
                                title=item,
                            )

    def _insert_memory(
        self,
        connection: sqlite3.Connection,
        *,
        run: ProcessingRun,
        project_key: str,
        kind: MemoryKind,
        content: str,
    ) -> None:
        normalized = _normalize_content(content)
        if not normalized:
            return
        connection.execute(
            """
            INSERT OR IGNORE INTO memories (
                id, project_key, kind, content, content_hash,
                source_run_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                project_key,
                kind,
                normalized,
                _content_hash(normalized),
                str(run.id),
                run.created_at.isoformat(),
            ),
        )

    def _insert_task(
        self,
        connection: sqlite3.Connection,
        *,
        run: ProcessingRun,
        project_key: str,
        title: str,
    ) -> None:
        normalized = _normalize_content(title)
        if not normalized:
            return
        timestamp = run.created_at.isoformat()
        connection.execute(
            """
            INSERT OR IGNORE INTO agent_tasks (
                id, project_key, title, content_hash, status,
                source_run_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'open', ?, ?, ?)
            """,
            (
                str(uuid4()),
                project_key,
                normalized,
                _content_hash(normalized),
                str(run.id),
                timestamp,
                timestamp,
            ),
        )

    def _initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS processing_runs (
                    id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL UNIQUE,
                    source TEXT NOT NULL,
                    project TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    status TEXT NOT NULL,
                    run_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agent_usage_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    estimated_tokens INTEGER NOT NULL
                        CHECK (estimated_tokens >= 0),
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES processing_runs(id)
                );

                CREATE TABLE IF NOT EXISTS model_processing_runs (
                    id TEXT PRIMARY KEY,
                    local_run_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    provider_requests INTEGER NOT NULL
                        CHECK (provider_requests >= 0),
                    provider_input_tokens INTEGER NOT NULL
                        CHECK (provider_input_tokens >= 0),
                    provider_output_tokens INTEGER NOT NULL
                        CHECK (provider_output_tokens >= 0),
                    provider_total_tokens INTEGER NOT NULL
                        CHECK (provider_total_tokens >= 0),
                    run_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (local_run_id, model),
                    FOREIGN KEY (local_run_id) REFERENCES processing_runs(id)
                );

                CREATE TABLE IF NOT EXISTS projects (
                    project_key TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_activity_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    project_key TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK (kind IN ('summary', 'decision')),
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    source_run_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (project_key, kind, content_hash),
                    FOREIGN KEY (project_key) REFERENCES projects(project_key),
                    FOREIGN KEY (source_run_id) REFERENCES processing_runs(id)
                );

                CREATE TABLE IF NOT EXISTS agent_tasks (
                    id TEXT PRIMARY KEY,
                    project_key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    status TEXT NOT NULL
                        CHECK (status IN ('open', 'done', 'dismissed')),
                    source_run_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (project_key, content_hash),
                    FOREIGN KEY (project_key) REFERENCES projects(project_key),
                    FOREIGN KEY (source_run_id) REFERENCES processing_runs(id)
                );

                CREATE TABLE IF NOT EXISTS agent_task_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    previous_status TEXT NOT NULL,
                    new_status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES agent_tasks(id)
                );

                CREATE INDEX IF NOT EXISTS memories_project_created
                ON memories(project_key, created_at DESC);

                CREATE INDEX IF NOT EXISTS agent_tasks_project_status
                ON agent_tasks(project_key, status, updated_at DESC);

                CREATE TRIGGER IF NOT EXISTS processing_runs_no_update
                BEFORE UPDATE ON processing_runs
                BEGIN
                    SELECT RAISE(ABORT, 'processing runs are immutable');
                END;

                CREATE TRIGGER IF NOT EXISTS processing_runs_no_delete
                BEFORE DELETE ON processing_runs
                BEGIN
                    SELECT RAISE(ABORT, 'processing runs are immutable');
                END;

                CREATE TRIGGER IF NOT EXISTS agent_usage_no_update
                BEFORE UPDATE ON agent_usage_events
                BEGIN
                    SELECT RAISE(ABORT, 'usage events are immutable');
                END;

                CREATE TRIGGER IF NOT EXISTS agent_usage_no_delete
                BEFORE DELETE ON agent_usage_events
                BEGIN
                    SELECT RAISE(ABORT, 'usage events are immutable');
                END;

                CREATE TRIGGER IF NOT EXISTS model_processing_runs_no_update
                BEFORE UPDATE ON model_processing_runs
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'model processing runs are immutable'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS model_processing_runs_no_delete
                BEFORE DELETE ON model_processing_runs
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'model processing runs are immutable'
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS memories_no_update
                BEFORE UPDATE ON memories
                BEGIN
                    SELECT RAISE(ABORT, 'memory records are immutable');
                END;

                CREATE TRIGGER IF NOT EXISTS memories_no_delete
                BEFORE DELETE ON memories
                BEGIN
                    SELECT RAISE(ABORT, 'memory records are immutable');
                END;

                CREATE TRIGGER IF NOT EXISTS agent_tasks_no_delete
                BEFORE DELETE ON agent_tasks
                BEGIN
                    SELECT RAISE(ABORT, 'agent tasks cannot be deleted');
                END;

                CREATE TRIGGER IF NOT EXISTS agent_tasks_identity_immutable
                BEFORE UPDATE ON agent_tasks
                WHEN NEW.id != OLD.id
                  OR NEW.project_key != OLD.project_key
                  OR NEW.title != OLD.title
                  OR NEW.content_hash != OLD.content_hash
                  OR NEW.source_run_id != OLD.source_run_id
                  OR NEW.created_at != OLD.created_at
                BEGIN
                    SELECT RAISE(ABORT, 'agent task identity is immutable');
                END;

                CREATE TRIGGER IF NOT EXISTS agent_task_events_no_update
                BEFORE UPDATE ON agent_task_events
                BEGIN
                    SELECT RAISE(ABORT, 'task events are immutable');
                END;

                CREATE TRIGGER IF NOT EXISTS agent_task_events_no_delete
                BEFORE DELETE ON agent_task_events
                BEGIN
                    SELECT RAISE(ABORT, 'task events are immutable');
                END;
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=5,
            check_same_thread=False,
        )
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @staticmethod
    def _run_from_row(row: sqlite3.Row | tuple | None) -> ProcessingRun | None:
        if row is None:
            return None
        return ProcessingRun.model_validate(json.loads(row[0]))

    def _get_by_fingerprint(
        self,
        connection: sqlite3.Connection,
        *,
        fingerprint: str,
    ) -> ProcessingRun | None:
        row = connection.execute(
            "SELECT run_json FROM processing_runs WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        return self._run_from_row(row)

    @staticmethod
    def _model_run_from_row(
        row: sqlite3.Row | tuple | None,
    ) -> ModelProcessingRun | None:
        if row is None:
            return None
        return ModelProcessingRun.model_validate(json.loads(row[0]))

    def _get_model_run_for_local(
        self,
        connection: sqlite3.Connection,
        *,
        local_run_id: UUID,
        model: str,
    ) -> ModelProcessingRun | None:
        row = connection.execute(
            """
            SELECT run_json
            FROM model_processing_runs
            WHERE local_run_id = ? AND model = ?
            """,
            (str(local_run_id), model),
        ).fetchone()
        return self._model_run_from_row(row)

    @staticmethod
    def _project_from_row(row: tuple) -> ProjectSummary:
        return ProjectSummary(
            key=row[0],
            name=row[1],
            memory_count=int(row[2]),
            open_task_count=int(row[3]),
            created_at=row[4],
            last_activity_at=row[5],
        )

    @staticmethod
    def _memory_from_row(row: tuple) -> MemoryRecord:
        return MemoryRecord(
            id=row[0],
            project_key=row[1],
            project=row[2],
            kind=row[3],
            content=row[4],
            source_run_id=row[5],
            created_at=row[6],
        )

    @staticmethod
    def _task_from_row(row: tuple) -> AgentTaskRecord:
        return AgentTaskRecord(
            id=row[0],
            project_key=row[1],
            project=row[2],
            title=row[3],
            status=row[4],
            source_run_id=row[5],
            created_at=row[6],
            updated_at=row[7],
        )

    @staticmethod
    def _get_task_row(
        connection: sqlite3.Connection,
        task_id: UUID,
    ) -> tuple | None:
        return connection.execute(
            """
            SELECT t.id, t.project_key, p.name, t.title, t.status,
                   t.source_run_id, t.created_at, t.updated_at
            FROM agent_tasks AS t
            JOIN projects AS p ON p.project_key = t.project_key
            WHERE t.id = ?
            """,
            (str(task_id),),
        ).fetchone()


def _normalize_content(value: str) -> str:
    return " ".join(value.split()).strip()


def _content_hash(value: str) -> str:
    return hashlib.sha256(value.casefold().encode("utf-8")).hexdigest()


def _project_key(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return normalized or "inbox"


def _search_terms(query: str) -> list[str]:
    candidates = re.findall(r"[a-z0-9][a-z0-9'-]+", query.casefold())
    terms: list[str] = []
    for candidate in candidates:
        if candidate in _SEARCH_STOPWORDS or candidate in terms:
            continue
        terms.append(candidate)
        if len(terms) == 8:
            break
    fallback = _normalize_content(query).casefold()
    return terms or ([fallback] if fallback else [])


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
