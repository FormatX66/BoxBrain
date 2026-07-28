import sqlite3

import pytest
from fastapi.testclient import TestClient

from boxbrain_controller import api
from boxbrain_controller.app import create_app
from boxbrain_controller.models import ProcessingRequest
from boxbrain_controller.processing_agents import ProcessingService
from boxbrain_controller.processing_store import ProcessingStore
from boxbrain_controller.settings import settings


@pytest.fixture
def service(tmp_path) -> ProcessingService:
    return ProcessingService(ProcessingStore(tmp_path / "boxbrain.sqlite3"))


def _artifact(run, kind: str):
    return next(artifact for artifact in run.artifacts if artifact.kind == kind)


def test_voice_intake_routes_the_main_processing_crew(service) -> None:
    run = service.process(
        ProcessingRequest(
            content=(
                "Build out out the main processing agents for Box Brain. "
                "Pull from recent voice chats and add GitHub sync."
            ),
            source="voice",
        )
    )

    agent_ids = [step.agent_id for step in run.steps]
    assert run.normalized_input.startswith("Build out the main")
    assert run.project == "BoxBrain"
    assert run.intent == "build"
    assert run.status == "needs_approval"
    assert agent_ids[:6] == [
        "orchestrator",
        "quartermaster",
        "sentinel",
        "librarian",
        "archivist",
        "task-manager",
    ]
    assert {"architect", "engineer", "integrator"} <= set(agent_ids)
    assert _artifact(run, "memory_note").data["project"] == "BoxBrain"
    assert _artifact(run, "integration_request").data["services"] == [
        "GitHub"
    ]
    assert run.usage.provider_tokens_used == 0


def test_quartermaster_defers_optional_agents_without_crashing(service) -> None:
    run = service.process(
        ProcessingRequest(
            content=(
                "Research and design a system, then build and test the code "
                "with a complete implementation workflow."
            ),
            source="voice",
            token_budget=128,
        )
    )

    assert run.status == "partially_deferred"
    assert run.usage.estimated_reserved_tokens <= 128
    assert run.usage.estimated_remaining_tokens >= 0
    assert run.usage.deferred_agents
    assert any(step.status == "deferred" for step in run.steps)


def test_duplicate_runs_are_reused_and_not_double_counted(service) -> None:
    request = ProcessingRequest(
        content="Organize this conversation into the Wet Beard project.",
        source="chat",
    )

    first = service.process(request)
    second = service.process(request)
    usage = service.usage_summary()

    assert second.id == first.id
    assert usage.total_runs == 1
    assert all(total.run_count == 1 for total in usage.by_agent)


def test_processing_runs_survive_restart_and_reject_mutation(tmp_path) -> None:
    database_path = tmp_path / "boxbrain.sqlite3"
    first_service = ProcessingService(ProcessingStore(database_path))
    run = first_service.process(
        ProcessingRequest(
            content="Create a project memory note for Brain Connect.",
            source="file",
        )
    )

    restarted = ProcessingService(ProcessingStore(database_path))
    assert restarted.get_run(run.id) == run

    with sqlite3.connect(database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE processing_runs SET status = 'completed' WHERE id = ?",
                (str(run.id),),
            )


def test_processing_api_exposes_agents_runs_and_usage(tmp_path, monkeypatch) -> None:
    service = ProcessingService(ProcessingStore(tmp_path / "boxbrain.sqlite3"))
    monkeypatch.setattr(api, "processing_service", service)
    headers = (
        {"X-BoxBrain-Token": settings.api_token}
        if settings.api_token is not None
        else {}
    )

    with TestClient(create_app(), headers=headers) as client:
        agents = client.get("/api/v1/agents")
        assert agents.status_code == 200
        assert len(agents.json()) == 10

        created = client.post(
            "/api/v1/processing/runs",
            json={
                "content": "Build the BoxBrain agent workflow.",
                "source": "voice",
            },
        )
        assert created.status_code == 200
        run_id = created.json()["id"]

        fetched = client.get(f"/api/v1/processing/runs/{run_id}")
        assert fetched.status_code == 200
        assert fetched.json()["id"] == run_id

        listed = client.get("/api/v1/processing/runs")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [run_id]

        usage = client.get("/api/v1/processing/usage")
        assert usage.status_code == 200
        assert usage.json()["total_runs"] == 1
        assert usage.json()["provider_tokens_used"] == 0


def test_blank_processing_input_is_rejected(tmp_path, monkeypatch) -> None:
    service = ProcessingService(ProcessingStore(tmp_path / "boxbrain.sqlite3"))
    monkeypatch.setattr(api, "processing_service", service)
    headers = (
        {"X-BoxBrain-Token": settings.api_token}
        if settings.api_token is not None
        else {}
    )

    with TestClient(create_app(), headers=headers) as client:
        response = client.post(
            "/api/v1/processing/runs",
            json={"content": "   ", "source": "voice"},
        )

    assert response.status_code == 422

def test_agents_materialize_projects_memory_and_tasks(service) -> None:
    run = service.process(
        ProcessingRequest(
            content=(
                "We decided to use SQLite for durable Box Brain memory. "
                "Build the memory search endpoint."
            ),
            source="voice",
        )
    )

    projects = service.list_projects()
    memories = service.list_memory(project="BoxBrain")
    tasks = service.list_agent_tasks(project="BoxBrain")
    dashboard = service.dashboard()

    assert projects[0].key == "boxbrain"
    assert projects[0].memory_count == 2
    assert projects[0].open_task_count == 1
    assert {memory.kind for memory in memories} == {"summary", "decision"}
    assert tasks[0].title == "Build the memory search endpoint."
    assert tasks[0].source_run_id == run.id
    assert dashboard.project_count == 1
    assert dashboard.memory_count == 2
    assert dashboard.open_task_count == 1


def test_scout_searches_existing_local_memory(service) -> None:
    service.process(
        ProcessingRequest(
            content="We decided Box Brain will use SQLite for durable memory.",
            source="voice",
        )
    )

    search_run = service.process(
        ProcessingRequest(
            content="Search memory for the SQLite decision in Box Brain.",
            source="voice",
        )
    )
    research = _artifact(search_run, "research_brief")
    direct_results = service.search_memory(
        query="SQLite decision",
        project="BoxBrain",
    )

    assert direct_results
    assert "SQLite" in direct_results[0].content
    assert research.data["local_memory_matches"]
    assert any(
        "SQLite" in result["content"]
        for result in research.data["local_memory_matches"]
    )


def test_task_manager_deduplicates_and_tracks_status(service) -> None:
    service.process(
        ProcessingRequest(
            content="Build the Box Brain memory index.",
            source="voice",
        )
    )
    service.process(
        ProcessingRequest(
            content=(
                "The architecture is approved. "
                "Build the Box Brain memory index."
            ),
            source="chat",
        )
    )

    tasks = service.list_agent_tasks(project="BoxBrain")
    assert len(tasks) == 1
    assert tasks[0].status == "open"

    completed = service.update_agent_task(tasks[0].id, task_status="done")
    dashboard = service.dashboard()

    assert completed is not None
    assert completed.status == "done"
    assert service.list_agent_tasks(task_status="open") == []
    assert dashboard.open_task_count == 0
    assert dashboard.completed_task_count == 1


def test_operational_agent_api_end_to_end(tmp_path, monkeypatch) -> None:
    service = ProcessingService(ProcessingStore(tmp_path / "boxbrain.sqlite3"))
    monkeypatch.setattr(api, "processing_service", service)
    headers = (
        {"X-BoxBrain-Token": settings.api_token}
        if settings.api_token is not None
        else {}
    )

    with TestClient(create_app(), headers=headers) as client:
        created = client.post(
            "/api/v1/processing/runs",
            json={
                "content": (
                    "We decided to keep Box Brain memory local. "
                    "Build the searchable memory dashboard."
                ),
                "source": "voice",
            },
        )
        assert created.status_code == 200

        projects = client.get("/api/v1/projects")
        assert projects.status_code == 200
        assert projects.json()[0]["key"] == "boxbrain"

        memory = client.get(
            "/api/v1/memory/search",
            params={"q": "local memory", "project": "BoxBrain"},
        )
        assert memory.status_code == 200
        assert memory.json()

        tasks = client.get(
            "/api/v1/agent-tasks",
            params={"project": "BoxBrain", "status": "open"},
        )
        assert tasks.status_code == 200
        task_id = tasks.json()[0]["id"]

        completed = client.post(
            f"/api/v1/agent-tasks/{task_id}/status",
            json={"status": "done"},
        )
        assert completed.status_code == 200
        assert completed.json()["status"] == "done"

        dashboard = client.get("/api/v1/agent-dashboard")
        assert dashboard.status_code == 200
        assert dashboard.json()["project_count"] == 1
        assert dashboard.json()["memory_count"] == 2
        assert dashboard.json()["open_task_count"] == 0
        assert dashboard.json()["completed_task_count"] == 1
