import asyncio
import sqlite3

from fastapi.testclient import TestClient

from boxbrain_controller import api
from boxbrain_controller.app import create_app
from boxbrain_controller.model_agents import (
    AgentRunnerResult,
    ModelAgentService,
    _provider_execution_error,
)
from boxbrain_controller.models import (
    ModelAgentPlan,
    ModelProviderUsage,
    ProcessingRequest,
)
from boxbrain_controller.processing_agents import ProcessingService
from boxbrain_controller.processing_store import ProcessingStore
from boxbrain_controller.settings import settings


class FakeRunner:
    def __init__(self) -> None:
        self.calls = 0
        self.prompts: list[str] = []

    async def run(self, prompt: str) -> AgentRunnerResult:
        self.calls += 1
        self.prompts.append(prompt)
        return AgentRunnerResult(
            plan=ModelAgentPlan(
                project="Untrusted model classification",
                intent="build",
                summary="Build the BoxBrain processing layer.",
                decisions=["Keep the deterministic path available."],
                tasks=["Implement the model-backed orchestrator."],
                specialist_handoffs=["architect", "engineer", "sentinel"],
                research_queries=[],
                architecture_notes=["Keep provider access behind an adapter."],
                implementation_steps=["Add typed output and isolated tests."],
                integration_requests=["Prepare a deployment handoff."],
                risk_flags=["Deployment requires operator approval."],
                requires_approval=False,
            ),
            usage=ModelProviderUsage(
                requests=1,
                input_tokens=80,
                output_tokens=40,
                total_tokens=120,
            ),
        )


def _service(tmp_path, runner=None, *, enabled=True) -> ModelAgentService:
    local_service = ProcessingService(
        ProcessingStore(tmp_path / "boxbrain.sqlite3")
    )
    return ModelAgentService(
        local_service,
        enabled=enabled,
        model="test-model",
        max_output_tokens=500,
        runner=runner,
    )


def _headers() -> dict[str, str]:
    return (
        {"X-BoxBrain-Token": settings.api_token}
        if settings.api_token is not None
        else {}
    )


def test_model_agent_run_is_grounded_persisted_and_deduplicated(
    tmp_path,
) -> None:
    runner = FakeRunner()
    service = _service(tmp_path, runner)
    request = ProcessingRequest(
        content="Build and deploy the BoxBrain processing agents.",
        source="voice",
    )

    first = asyncio.run(service.process(request))
    second = asyncio.run(service.process(request))

    assert second.id == first.id
    assert runner.calls == 1
    assert first.plan.project == "BoxBrain"
    assert first.plan.requires_approval is True
    assert first.usage.total_tokens == 120
    assert service.get_run(first.id) == first
    assert service.list_runs() == [first]
    assert service.local_service.usage_summary().provider_tokens_used == 120
    assert "external_access_allowed" in runner.prompts[0]


def test_model_agent_runs_are_immutable(tmp_path) -> None:
    runner = FakeRunner()
    service = _service(tmp_path, runner)
    run = asyncio.run(
        service.process(
            ProcessingRequest(
                content="Build the BoxBrain agent runtime.",
                source="chat",
            )
        )
    )

    with sqlite3.connect(service.store.database_path) as connection:
        try:
            connection.execute(
                "UPDATE model_processing_runs SET model = ? WHERE id = ?",
                ("changed", str(run.id)),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("Model processing runs must be immutable")


def test_model_agent_api_exposes_runtime_and_runs(
    tmp_path,
    monkeypatch,
) -> None:
    service = _service(tmp_path, FakeRunner())
    monkeypatch.setattr(api, "model_agent_service", service)

    with TestClient(create_app(), headers=_headers()) as client:
        runtime = client.get("/api/v1/agents/runtime")
        assert runtime.status_code == 200
        assert runtime.json() == {
            "enabled": True,
            "configured": True,
            "sdk_available": True,
            "ready": True,
            "model": "test-model",
            "execution_mode": "openai-agents-sdk",
            "external_side_effects_enabled": False,
        }

        created = client.post(
            "/api/v1/processing/model-runs",
            json={
                "content": "Build the BoxBrain processing agents.",
                "source": "voice",
            },
        )
        assert created.status_code == 200
        run_id = created.json()["id"]

        fetched = client.get(f"/api/v1/processing/model-runs/{run_id}")
        assert fetched.status_code == 200
        assert fetched.json()["id"] == run_id

        listed = client.get("/api/v1/processing/model-runs")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [run_id]


def test_disabled_model_runtime_returns_unavailable_without_local_write(
    tmp_path,
    monkeypatch,
) -> None:
    service = _service(tmp_path, enabled=False)
    monkeypatch.setattr(api, "model_agent_service", service)

    with TestClient(create_app(), headers=_headers()) as client:
        response = client.post(
            "/api/v1/processing/model-runs",
            json={"content": "Build the agent runtime.", "source": "voice"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "The model-agent runtime is disabled."
    assert service.local_service.list_runs() == []

def test_insufficient_quota_is_not_misreported_as_rate_limiting() -> None:
    class ProviderError(Exception):
        status_code = 429
        code = "insufficient_quota"
        body = {"code": "insufficient_quota"}

    error = _provider_execution_error(ProviderError())

    assert error.category == "quota"
    assert str(error) == (
        "OpenAI API quota is unavailable; check API billing or limits."
    )
