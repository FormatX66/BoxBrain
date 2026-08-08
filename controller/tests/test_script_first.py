from pathlib import Path

from fastapi.testclient import TestClient

from boxbrain_controller import api
from boxbrain_controller.app import create_app
from boxbrain_controller.script_first import (
    RouteRequest,
    ScriptFirstService,
    ScriptRunRequest,
    TaskRoute,
)
from boxbrain_controller.settings import settings


def _service(tmp_path: Path) -> ScriptFirstService:
    repository = tmp_path / "repo"
    (repository / ".codex" / "queue").mkdir(parents=True)
    (repository / ".codex" / "queue" / "QUEUE.md").write_text(
        "[TASK BB-006]\nSTATUS: PENDING\n", encoding="utf-8"
    )
    (repository / ".codex" / "queue" / "COMPLETE.md").write_text(
        "# Complete\n", encoding="utf-8"
    )
    return ScriptFirstService(repository, tmp_path / "state")


def test_router_prefers_registered_script_for_deterministic_work(tmp_path) -> None:
    service = _service(tmp_path)
    decision = service.classify(
        RouteRequest(
            task_id="BB-006",
            description="Summarize a repetitive JSONL log.",
            script_id="jsonl.summary",
            deterministic=True,
            repetitive=True,
            data_heavy=True,
            model_lane="future-low-cost",
        )
    )

    assert decision.route is TaskRoute.SCRIPT
    assert decision.confidence >= 0.95
    assert decision.fallback is TaskRoute.HYBRID
    assert decision.queue_state == "active"
    assert decision.model_lane == "future-low-cost"


def test_router_uses_gpt_for_ambiguity_and_hybrid_for_high_impact(tmp_path) -> None:
    service = _service(tmp_path)
    ambiguous = service.classify(
        RouteRequest(description="Diagnose an unknown failure.", ambiguous=True)
    )
    high_impact = service.classify(
        RouteRequest(description="Change a live service.", high_impact=True)
    )

    assert ambiguous.route is TaskRoute.GPT
    assert high_impact.route is TaskRoute.HYBRID
    assert high_impact.human_review_required is True


def test_builtins_return_compact_structured_results(tmp_path) -> None:
    service = _service(tmp_path)
    summary = service.execute(
        ScriptRunRequest(
            task_id="BB-006",
            script_id="jsonl.summary",
            payload={"text": '{"ok":true}\nnot-json\n{"ok":false,"value":2}'},
            idempotency_key="bb-006-jsonl-1",
        )
    )
    diff = service.execute(
        ScriptRunRequest(
            script_id="text.diff",
            payload={"before": "one\ntwo", "after": "one\nthree"},
            idempotency_key="diff-1",
        )
    )

    assert summary.status == "succeeded"
    assert summary.avoided_model_call is True
    assert summary.data["records"] == 2
    assert len(summary.data["errors"]) == 1
    assert diff.data["added"] == 1
    assert diff.data["removed"] == 1


def test_idempotency_and_complete_log_prevent_duplicate_work(tmp_path) -> None:
    service = _service(tmp_path)
    request = ScriptRunRequest(
        script_id="text.summary",
        payload={"text": "repeat me"},
        idempotency_key="same-key",
    )
    assert service.execute(request).status == "succeeded"
    assert service.execute(request).status == "duplicate"

    complete = service.repository_root / ".codex" / "queue" / "COMPLETE.md"
    complete.write_text("BB-006 verified complete\n", encoding="utf-8")
    complete_result = service.execute(
        ScriptRunRequest(
            task_id="BB-006",
            script_id="text.summary",
            payload={"text": "do not run"},
            idempotency_key="complete-task",
        )
    )
    assert complete_result.status == "duplicate"

    metrics = service.metrics()
    assert metrics.avoided_model_calls == 3
    assert metrics.duplicate_runs_prevented == 2


def test_inventory_is_repository_bounded_and_errors_escalate(tmp_path) -> None:
    service = _service(tmp_path)
    (service.repository_root / "sample.txt").write_text("sample", encoding="utf-8")
    successful = service.execute(
        ScriptRunRequest(
            script_id="files.inventory",
            payload={"path": ".", "max_files": 20},
            idempotency_key="inventory-good",
        )
    )
    escaped = service.execute(
        ScriptRunRequest(
            script_id="files.inventory",
            payload={"path": "..", "max_files": 20},
            idempotency_key="inventory-escape",
        )
    )

    assert successful.status == "succeeded"
    assert any(item["path"] == "sample.txt" for item in successful.data["files"])
    assert escaped.status == "escalated"
    assert escaped.fallback is TaskRoute.GPT
    assert "path must remain" in escaped.data["error"]


def test_script_first_api_exposes_registry_route_run_and_metrics(
    tmp_path, monkeypatch
) -> None:
    service = _service(tmp_path)
    monkeypatch.setattr(api, "script_first_service", service)
    headers = (
        {"X-BoxBrain-Token": settings.api_token}
        if settings.api_token is not None
        else {}
    )

    with TestClient(create_app(), headers=headers) as client:
        registry = client.get("/api/v1/processing/script-registry")
        assert registry.status_code == 200
        assert {item["id"] for item in registry.json()} >= {
            "text.summary",
            "jsonl.summary",
            "text.diff",
            "files.inventory",
        }

        route = client.post(
            "/api/v1/processing/route",
            json={
                "description": "Summarize logs",
                "script_id": "text.summary",
                "deterministic": True,
            },
        )
        assert route.status_code == 200
        assert route.json()["route"] == "script"

        run = client.post(
            "/api/v1/processing/script-runs",
            json={
                "script_id": "text.summary",
                "payload": {"text": "hello world"},
                "idempotency_key": "api-summary-1",
            },
        )
        assert run.status_code == 200
        assert run.json()["status"] == "succeeded"

        metrics = client.get("/api/v1/processing/script-metrics")
        assert metrics.status_code == 200
        assert metrics.json()["avoided_model_calls"] == 1
