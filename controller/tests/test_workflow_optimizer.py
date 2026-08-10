from pathlib import Path

from fastapi.testclient import TestClient

from boxbrain_controller import api
from boxbrain_controller.app import create_app
from boxbrain_controller.copilot_offload import (
    GITHUB_COPILOT_SEND_CONFIRMATION,
    CopilotOffloadService,
    CopilotProvider,
    CopilotTaskKind,
)
from boxbrain_controller.script_first import ScriptFirstService
from boxbrain_controller.settings import settings
from boxbrain_controller.workflow_optimizer import (
    WorkflowLane,
    WorkflowOptimizeRequest,
    WorkflowOptimizerService,
)


def _service(
    tmp_path: Path,
    *,
    github_installed: bool = True,
    github_enabled: bool = True,
    windows_installed: bool = True,
) -> WorkflowOptimizerService:
    repository = tmp_path / "repo"
    (repository / ".codex" / "queue").mkdir(parents=True)
    (repository / ".codex" / "queue" / "QUEUE.md").write_text(
        "[TASK BB-007]\nSTATUS: IN_PROGRESS\n",
        encoding="utf-8",
    )
    (repository / ".codex" / "queue" / "COMPLETE.md").write_text(
        "# Complete\n",
        encoding="utf-8",
    )
    script_service = ScriptFirstService(repository, tmp_path / "state")
    copilot_service = CopilotOffloadService(
        repository,
        tmp_path / "state",
        enabled=github_enabled,
        cli_finder=(
            (lambda _name: "C:\\Program Files\\GitHub Copilot\\copilot.exe")
            if github_installed
            else (lambda _name: None)
        ),
        windows_app_detector=lambda: windows_installed,
    )
    return WorkflowOptimizerService(script_service, copilot_service)


def test_registered_local_script_wins_without_external_model_call(tmp_path) -> None:
    plan = _service(tmp_path).optimize(
        WorkflowOptimizeRequest(
            task_id="BB-007",
            description="Summarize this deterministic text.",
            script_id="text.summary",
            deterministic=True,
            repetitive=True,
            copilot_kind=CopilotTaskKind.WINDOWS_CODE,
            preferred_provider=CopilotProvider.WINDOWS_COPILOT_APP,
        )
    )

    assert plan.selected_lane is WorkflowLane.LOCAL_SCRIPT
    assert plan.provider is None
    assert plan.estimated_external_model_calls == 0
    assert plan.action_taken is False
    assert all(step.automatic is False for step in plan.steps)


def test_windows_code_routes_to_guarded_github_copilot_workflow(tmp_path) -> None:
    plan = _service(tmp_path).optimize(
        WorkflowOptimizeRequest(
            task_id="BB-007",
            description="Review a local Windows PowerShell helper.",
            requires_reasoning=True,
            copilot_kind=CopilotTaskKind.WINDOWS_CODE,
        )
    )

    assert plan.selected_lane is WorkflowLane.GITHUB_COPILOT
    assert plan.provider is CopilotProvider.GITHUB_COPILOT_CLI
    assert plan.provider_display_name == "GitHub Copilot CLI"
    assert plan.dispatch_mode == "guarded_automation"
    assert plan.dispatch_available is True
    assert plan.confirmation_phrase == GITHUB_COPILOT_SEND_CONFIRMATION
    assert plan.human_review_required is True
    assert plan.estimated_external_model_calls == 1
    assert any(step.requires_confirmation for step in plan.steps)
    assert plan.action_taken is False


def test_registered_preprocessing_can_reduce_github_packet_scope(tmp_path) -> None:
    plan = _service(tmp_path).optimize(
        WorkflowOptimizeRequest(
            description="Inventory files, then propose a clearer organization.",
            script_id="files.inventory",
            requires_reasoning=True,
            data_heavy=True,
            copilot_kind=CopilotTaskKind.FILE_ORGANIZATION,
        )
    )

    assert plan.selected_lane is WorkflowLane.HYBRID_GITHUB_COPILOT
    assert plan.steps[0].lane is WorkflowLane.LOCAL_SCRIPT
    assert plan.steps[1].lane is WorkflowLane.HYBRID_GITHUB_COPILOT
    assert "reduce the external reasoning scope" in plan.reasons[0]


def test_windows_copilot_is_explicit_manual_only_workflow(tmp_path) -> None:
    plan = _service(tmp_path).optimize(
        WorkflowOptimizeRequest(
            description="Ask for general Windows organization advice.",
            requires_reasoning=True,
            copilot_kind=CopilotTaskKind.FILE_ORGANIZATION,
            preferred_provider=CopilotProvider.WINDOWS_COPILOT_APP,
        )
    )

    assert plan.selected_lane is WorkflowLane.WINDOWS_COPILOT_MANUAL
    assert plan.provider is CopilotProvider.WINDOWS_COPILOT_APP
    assert plan.provider_display_name == "Microsoft Copilot (Windows app)"
    assert plan.provider_installed is True
    assert plan.dispatch_mode == "manual_only"
    assert plan.dispatch_available is False
    assert plan.confirmation_phrase is None
    assert any(step.effect == "manual" for step in plan.steps)
    assert all(step.automatic is False for step in plan.steps)


def test_high_impact_work_never_routes_to_either_copilot(tmp_path) -> None:
    plan = _service(tmp_path).optimize(
        WorkflowOptimizeRequest(
            description="Change a live Windows service.",
            high_impact=True,
            copilot_kind=CopilotTaskKind.WINDOWS_CODE,
            preferred_provider=CopilotProvider.GITHUB_COPILOT_CLI,
        )
    )

    assert plan.selected_lane is WorkflowLane.HUMAN_REVIEW
    assert plan.provider is None
    assert plan.dispatch_available is False
    assert plan.estimated_external_model_calls == 0
    assert plan.human_review_required is True


def test_workflow_optimizer_api_returns_advice_without_execution(
    tmp_path, monkeypatch
) -> None:
    service = _service(tmp_path, github_enabled=False)
    monkeypatch.setattr(api, "workflow_optimizer_service", service)
    headers = (
        {"X-BoxBrain-Token": settings.api_token}
        if settings.api_token is not None
        else {}
    )

    with TestClient(create_app(), headers=headers) as client:
        response = client.post(
            "/api/v1/processing/workflows/optimize",
            json={
                "task_id": "BB-007",
                "description": "Review a plugin manifest.",
                "requires_reasoning": True,
                "copilot_kind": "plugin_code",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["selected_lane"] == "github_copilot"
    assert body["provider"] == "github-copilot-cli"
    assert body["dispatch_available"] is False
    assert body["confirmation_phrase"] == "SEND TO GITHUB COPILOT"
    assert body["action_taken"] is False
