from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from uuid import uuid4

from .models import (
    ChatOrganizerDashboard,
    ChatOrganizerImportRequest,
    ChatOrganizerImportResult,
    ChatProjectBucket,
    ChatSourceRecord,
    OrganizedChatRecord,
)


_PROJECT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "BoxBrain & AI Agents",
        (
            "agent",
            "ai os",
            "box brain",
            "boxbrain",
            "chatgpt",
            "codex",
            "workflow",
        ),
    ),
    (
        "Websites & Content",
        (
            "bluehost",
            "campaign",
            "instagram",
            "morri",
            "social media",
            "video",
            "website",
        ),
    ),
    (
        "Accounts & Storage",
        (
            "access",
            "case",
            "github",
            "gmail",
            "google drive",
            "google photos",
            "mailbox",
            "openai support",
            "repo",
            "storage",
        ),
    ),
    (
        "Devices & Remote Access",
        (
            "cable",
            "ios",
            "kali",
            "remote access",
            "voice control",
        ),
    ),
    (
        "Creative Ideas",
        (
            "arkmatx",
            "clown",
            "mad magazine",
            "surprise",
        ),
    ),
)


class ChatOrganizerService:
    """Durable, read-only organizer for ChatGPT chat metadata."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self._lock = RLock()
        self._initialize()

    def import_snapshot(
        self,
        request: ChatOrganizerImportRequest,
    ) -> ChatOrganizerImportResult:
        imported_at = datetime.now(UTC)
        run_id = uuid4()
        project_labels = {
            project.external_id: project.label for project in request.projects
        }
        created_count = 0
        updated_count = 0
        unchanged_count = 0
        unassigned_count = 0
        suggested_move_count = 0

        with self._lock, self._connect() as connection:
            for project in request.projects:
                connection.execute(
                    """
                    INSERT INTO chat_source_projects (
                        external_id, label, last_seen_at
                    ) VALUES (?, ?, ?)
                    ON CONFLICT(external_id) DO UPDATE SET
                        label = excluded.label,
                        last_seen_at = excluded.last_seen_at
                    """,
                    (
                        project.external_id,
                        project.label,
                        imported_at.isoformat(),
                    ),
                )

            for chat in request.chats:
                current_project = (
                    project_labels.get(chat.project_external_id)
                    if chat.project_external_id is not None
                    else None
                )
                suggestion, reason, confidence = _classify(
                    chat,
                    current_project=current_project,
                )
                if current_project is None:
                    unassigned_count += 1
                    if suggestion != "Inbox / Needs Review":
                        suggested_move_count += 1

                values = (
                    chat.title,
                    chat.project_external_id,
                    current_project,
                    suggestion,
                    reason,
                    confidence,
                    chat.pinned_index,
                    chat.updated_at.isoformat(),
                    imported_at.isoformat(),
                )
                existing = connection.execute(
                    """
                    SELECT title, current_project_id, current_project,
                           suggested_project, classification_reason,
                           confidence, pinned_index, updated_at
                    FROM organized_chats
                    WHERE external_id = ?
                    """,
                    (chat.external_id,),
                ).fetchone()
                comparable = values[:-1]
                if existing is None:
                    created_count += 1
                elif tuple(existing) == comparable:
                    unchanged_count += 1
                else:
                    updated_count += 1

                connection.execute(
                    """
                    INSERT INTO organized_chats (
                        external_id, title, current_project_id,
                        current_project, suggested_project,
                        classification_reason, confidence, pinned_index,
                        updated_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(external_id) DO UPDATE SET
                        title = excluded.title,
                        current_project_id = excluded.current_project_id,
                        current_project = excluded.current_project,
                        suggested_project = excluded.suggested_project,
                        classification_reason = excluded.classification_reason,
                        confidence = excluded.confidence,
                        pinned_index = excluded.pinned_index,
                        updated_at = excluded.updated_at,
                        last_seen_at = excluded.last_seen_at
                    """,
                    (chat.external_id, *values),
                )

            result = ChatOrganizerImportResult(
                id=run_id,
                source=request.source,
                captured_at=request.captured_at,
                imported_at=imported_at,
                source_project_count=len(request.projects),
                chat_count=len(request.chats),
                created_count=created_count,
                updated_count=updated_count,
                unchanged_count=unchanged_count,
                unassigned_count=unassigned_count,
                suggested_move_count=suggested_move_count,
            )
            connection.execute(
                """
                INSERT INTO chat_organizer_imports (
                    id, source, captured_at, imported_at,
                    source_project_count, chat_count, created_count,
                    updated_count, unchanged_count, unassigned_count,
                    suggested_move_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(result.id),
                    result.source,
                    result.captured_at.isoformat(),
                    result.imported_at.isoformat(),
                    result.source_project_count,
                    result.chat_count,
                    result.created_count,
                    result.updated_count,
                    result.unchanged_count,
                    result.unassigned_count,
                    result.suggested_move_count,
                ),
            )
        return result

    def dashboard(self) -> ChatOrganizerDashboard:
        with self._lock, self._connect() as connection:
            totals = connection.execute(
                """
                SELECT
                    COUNT(*),
                    COUNT(DISTINCT current_project_id),
                    SUM(CASE WHEN current_project_id IS NULL THEN 1 ELSE 0 END),
                    SUM(CASE
                        WHEN current_project_id IS NULL
                         AND suggested_project != 'Inbox / Needs Review'
                        THEN 1 ELSE 0 END),
                    SUM(CASE WHEN pinned_index IS NOT NULL THEN 1 ELSE 0 END)
                FROM organized_chats
                """
            ).fetchone()
            last_sync = connection.execute(
                """
                SELECT imported_at
                FROM chat_organizer_imports
                ORDER BY imported_at DESC
                LIMIT 1
                """
            ).fetchone()
            bucket_rows = connection.execute(
                """
                SELECT
                    suggested_project,
                    COUNT(*),
                    MAX(CASE WHEN current_project IS NOT NULL THEN 1 ELSE 0 END)
                FROM organized_chats
                GROUP BY suggested_project
                ORDER BY COUNT(*) DESC, suggested_project ASC
                """
            ).fetchall()
            source_project_rows = connection.execute(
                """
                SELECT label
                FROM chat_source_projects
                ORDER BY label ASC
                """
            ).fetchall()

        bucket_names = {row[0] for row in bucket_rows}
        return ChatOrganizerDashboard(
            total_chat_count=int(totals[0]) if totals else 0,
            source_project_count=len(source_project_rows),
            unassigned_count=int(totals[2] or 0) if totals else 0,
            suggested_move_count=int(totals[3] or 0) if totals else 0,
            pinned_count=int(totals[4] or 0) if totals else 0,
            last_sync_at=(
                datetime.fromisoformat(last_sync[0]) if last_sync else None
            ),
            buckets=[
                *[
                    ChatProjectBucket(
                        name=row[0],
                        chat_count=int(row[1]),
                        is_existing_chatgpt_project=bool(row[2]),
                    )
                    for row in bucket_rows
                ],
                *[
                    ChatProjectBucket(
                        name=row[0],
                        chat_count=0,
                        is_existing_chatgpt_project=True,
                    )
                    for row in source_project_rows
                    if row[0] not in bucket_names
                ],
            ],
            recent_chats=self.list_chats(limit=12),
        )

    def list_chats(
        self,
        *,
        project: str | None = None,
        unassigned_only: bool = False,
        limit: int = 100,
    ) -> list[OrganizedChatRecord]:
        clauses: list[str] = []
        parameters: list[object] = []
        if project is not None:
            clauses.append("suggested_project = ?")
            parameters.append(project)
        if unassigned_only:
            clauses.append("current_project_id IS NULL")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(limit)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT external_id, title, current_project_id,
                       current_project, suggested_project,
                       classification_reason, confidence, pinned_index,
                       updated_at, last_seen_at
                FROM organized_chats
                {where}
                ORDER BY
                    CASE WHEN pinned_index IS NULL THEN 1 ELSE 0 END,
                    pinned_index ASC,
                    updated_at DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [_chat_from_row(row) for row in rows]

    def list_imports(
        self,
        *,
        limit: int = 50,
    ) -> list[ChatOrganizerImportResult]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, source, captured_at, imported_at,
                       source_project_count, chat_count, created_count,
                       updated_count, unchanged_count, unassigned_count,
                       suggested_move_count
                FROM chat_organizer_imports
                ORDER BY imported_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            ChatOrganizerImportResult(
                id=row[0],
                source=row[1],
                captured_at=datetime.fromisoformat(row[2]),
                imported_at=datetime.fromisoformat(row[3]),
                source_project_count=int(row[4]),
                chat_count=int(row[5]),
                created_count=int(row[6]),
                updated_count=int(row[7]),
                unchanged_count=int(row[8]),
                unassigned_count=int(row[9]),
                suggested_move_count=int(row[10]),
            )
            for row in rows
        ]

    def _initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS chat_source_projects (
                    external_id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS organized_chats (
                    external_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    current_project_id TEXT,
                    current_project TEXT,
                    suggested_project TEXT NOT NULL,
                    classification_reason TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    pinned_index INTEGER,
                    updated_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_organized_chats_suggestion
                ON organized_chats(suggested_project, updated_at DESC);

                CREATE INDEX IF NOT EXISTS idx_organized_chats_unassigned
                ON organized_chats(current_project_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS chat_organizer_imports (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    imported_at TEXT NOT NULL,
                    source_project_count INTEGER NOT NULL,
                    chat_count INTEGER NOT NULL,
                    created_count INTEGER NOT NULL,
                    updated_count INTEGER NOT NULL,
                    unchanged_count INTEGER NOT NULL,
                    unassigned_count INTEGER NOT NULL,
                    suggested_move_count INTEGER NOT NULL
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection


def _classify(
    chat: ChatSourceRecord,
    *,
    current_project: str | None,
) -> tuple[str, str, str]:
    if current_project is not None:
        return (
            current_project,
            "Already organized in a ChatGPT project.",
            "high",
        )

    normalized_title = chat.title.casefold()
    for project, keywords in _PROJECT_RULES:
        match = next(
            (keyword for keyword in keywords if keyword in normalized_title),
            None,
        )
        if match is not None:
            return (
                project,
                f'Title matched the "{match}" organization rule.',
                "medium",
            )
    return (
        "Inbox / Needs Review",
        "No reliable title match; kept in the review inbox.",
        "low",
    )


def _chat_from_row(row: sqlite3.Row | tuple) -> OrganizedChatRecord:
    return OrganizedChatRecord(
        external_id=row[0],
        title=row[1],
        current_project_id=row[2],
        current_project=row[3],
        suggested_project=row[4],
        classification_reason=row[5],
        confidence=row[6],
        pinned_index=row[7],
        updated_at=datetime.fromisoformat(row[8]),
        last_seen_at=datetime.fromisoformat(row[9]),
    )
