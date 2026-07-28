from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from boxbrain_controller import api
from boxbrain_controller.app import create_app
from boxbrain_controller.chat_organizer import ChatOrganizerService
from boxbrain_controller.models import ChatOrganizerImportRequest
from boxbrain_controller.settings import settings


def _snapshot() -> ChatOrganizerImportRequest:
    captured_at = datetime(2026, 7, 28, 14, tzinfo=UTC)
    return ChatOrganizerImportRequest.model_validate(
        {
            "source": "chatgpt_app_index",
            "captured_at": captured_at,
            "projects": [
                {
                    "external_id": "g-p-wet-beard",
                    "label": "Wet Beard website",
                },
                {
                    "external_id": "g-p-empty",
                    "label": "Quest cards",
                },
            ],
            "chats": [
                {
                    "external_id": "chat-project",
                    "title": "GitHub Relay Mobile Access",
                    "updated_at": captured_at,
                    "project_external_id": "g-p-wet-beard",
                    "pinned_index": 1,
                },
                {
                    "external_id": "chat-boxbrain",
                    "title": "BoxBrain Repo Access",
                    "updated_at": captured_at - timedelta(minutes=1),
                },
                {
                    "external_id": "chat-website",
                    "title": "Building Morri Website",
                    "updated_at": captured_at - timedelta(minutes=2),
                },
                {
                    "external_id": "chat-review",
                    "title": "Dumb logic discussion",
                    "updated_at": captured_at - timedelta(minutes=3),
                },
            ],
        }
    )


def test_import_preserves_projects_classifies_loose_chats_and_deduplicates(
    tmp_path,
) -> None:
    service = ChatOrganizerService(tmp_path / "boxbrain.sqlite3")

    first = service.import_snapshot(_snapshot())
    second = service.import_snapshot(_snapshot())
    dashboard = service.dashboard()
    chats = {chat.external_id: chat for chat in service.list_chats()}

    assert first.created_count == 4
    assert first.updated_count == 0
    assert first.unchanged_count == 0
    assert first.unassigned_count == 3
    assert first.suggested_move_count == 2
    assert second.created_count == 0
    assert second.updated_count == 0
    assert second.unchanged_count == 4

    assert chats["chat-project"].current_project == "Wet Beard website"
    assert chats["chat-project"].suggested_project == "Wet Beard website"
    assert chats["chat-project"].confidence == "high"
    assert chats["chat-boxbrain"].suggested_project == "BoxBrain & AI Agents"
    assert chats["chat-website"].suggested_project == "Websites & Content"
    assert chats["chat-review"].suggested_project == "Inbox / Needs Review"
    assert dashboard.total_chat_count == 4
    assert dashboard.source_project_count == 2
    assert dashboard.unassigned_count == 3
    assert dashboard.suggested_move_count == 2
    assert dashboard.pinned_count == 1
    assert dashboard.last_sync_at is not None
    empty_bucket = next(
        bucket for bucket in dashboard.buckets if bucket.name == "Quest cards"
    )
    assert empty_bucket.chat_count == 0
    assert empty_bucket.is_existing_chatgpt_project is True


def test_import_updates_changed_chat_without_creating_duplicate(tmp_path) -> None:
    service = ChatOrganizerService(tmp_path / "boxbrain.sqlite3")
    service.import_snapshot(_snapshot())
    changed = _snapshot().model_copy(deep=True)
    changed.chats[1].title = "BoxBrain agent dashboard"
    changed.chats[1].updated_at += timedelta(hours=1)

    result = service.import_snapshot(changed)
    matches = service.list_chats(project="BoxBrain & AI Agents")

    assert result.created_count == 0
    assert result.updated_count == 1
    assert result.unchanged_count == 3
    assert [chat.title for chat in matches] == ["BoxBrain agent dashboard"]


def test_chat_organizer_api_end_to_end(tmp_path, monkeypatch) -> None:
    service = ChatOrganizerService(tmp_path / "boxbrain.sqlite3")
    monkeypatch.setattr(api, "chat_organizer_service", service)
    headers = (
        {"X-BoxBrain-Token": settings.api_token}
        if settings.api_token is not None
        else {}
    )

    with TestClient(create_app(), headers=headers) as client:
        imported = client.post(
            "/api/v1/chat-organizer/import",
            json=_snapshot().model_dump(mode="json"),
        )
        dashboard = client.get("/api/v1/chat-organizer")
        unassigned = client.get(
            "/api/v1/chat-organizer/chats",
            params={"unassigned_only": True},
        )
        imports = client.get("/api/v1/chat-organizer/imports")

    assert imported.status_code == 200
    assert imported.json()["chat_count"] == 4
    assert dashboard.status_code == 200
    assert dashboard.json()["total_chat_count"] == 4
    assert len(unassigned.json()) == 3
    assert imports.json()[0]["id"] == imported.json()["id"]
