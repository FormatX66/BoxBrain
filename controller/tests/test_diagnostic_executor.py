from __future__ import annotations

import asyncio
import socket
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from boxbrain_controller import api
from boxbrain_controller.app import create_app
from boxbrain_controller.diagnostic_executor import (
    DiagnosticCommandResult,
    DiagnosticError,
    DiagnosticExecutorService,
    DiagnosticPlannerResult,
)
from boxbrain_controller.models import (
    DiagnosticPlan,
    DiagnosticProposalRequest,
    DiagnosticProviderUsage,
    RemoteTargetCreate,
)
from boxbrain_controller.remote_targets import RemoteTargetService
from boxbrain_controller.task_store import TaskStore


class _Planner:
    def __init__(self, action: str = "disk_usage") -> None:
        self.action = action
        self.goals: list[str] = []

    async def run(
        self,
        *,
        goal: str,
        target_name: str,
    ) -> DiagnosticPlannerResult:
        self.goals.append(goal)
        assert target_name == "Kali Pi USB-C"
        return DiagnosticPlannerResult(
            plan=DiagnosticPlan(
                action=self.action,
                summary="Collect fixed read-only disk usage evidence.",
                expected_evidence="Filesystem size, used, and available bytes.",
                risk_note="Read-only diagnostic; no files are changed.",
            ),
            usage=DiagnosticProviderUsage(
                requests=1,
                input_tokens=40,
                output_tokens=20,
                total_tokens=60,
            ),
        )


def _private_resolver(host: str, port: int) -> list[tuple[Any, ...]]:
    return [
        (
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            ("10.12.194.1", port),
        )
    ]


def _services(
    tmp_path: Path,
    *,
    planner: _Planner | None = None,
    command_runner=None,
) -> tuple[RemoteTargetService, DiagnosticExecutorService]:
    database = tmp_path / "boxbrain.sqlite3"
    target_service = RemoteTargetService(
        database,
        resolver=_private_resolver,
        launcher=lambda command: None,
    )
    executor = DiagnosticExecutorService(
        database,
        target_service,
        enabled=True,
        model="test-model",
        max_output_tokens=500,
        planner=planner or _Planner(),
        command_runner=command_runner
        or (
            lambda command, timeout: DiagnosticCommandResult(
                exit_code=0,
                stdout="Filesystem 1B-blocks Used Available Capacity Mounted on\n"
                "/dev/root 1000 400 600 40% /",
                stderr="",
            )
        ),
    )
    return target_service, executor


def _proposal_request(goal: str = "Check disk space on the Pi") -> DiagnosticProposalRequest:
    return DiagnosticProposalRequest(
        goal=goal,
        authorization="AUTHORIZED",
    )


def test_ai_proposal_is_durable_and_executes_only_fixed_command(
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []
    planner = _Planner()

    def run_command(command: list[str], timeout: float) -> DiagnosticCommandResult:
        commands.append(command)
        assert timeout == 20.0
        return DiagnosticCommandResult(
            exit_code=0,
            stdout="/dev/root 1000 400 600 40% /",
            stderr="",
        )

    target_service, executor = _services(
        tmp_path,
        planner=planner,
        command_runner=run_command,
    )
    target = target_service.list()[0]
    goal = "Check disk; echo unsafe-user-text"

    proposal = asyncio.run(executor.propose(target.id, _proposal_request(goal)))

    assert proposal.plan.action == "disk_usage"
    assert proposal.requires_confirmation is True
    assert proposal.usage.total_tokens == 60
    assert executor.list(target_id=target.id)[0].id == proposal.id

    result = executor.execute(proposal.id)

    assert result.status == "succeeded"
    assert result.output.startswith("/dev/root")
    assert commands[0][-1] == "LC_ALL=C df -P -B1 --local"
    assert goal not in " ".join(commands[0])
    assert commands[0][:4] == ["ssh", "-o", "BatchMode=yes", "-o"]
    with pytest.raises(DiagnosticError, match="cannot run"):
        executor.execute(proposal.id)


def test_diagnostic_output_is_capped_and_failure_is_recorded(
    tmp_path: Path,
) -> None:
    target_service, executor = _services(
        tmp_path,
        command_runner=lambda command, timeout: DiagnosticCommandResult(
            exit_code=2,
            stdout="x" * 100,
            stderr="fixed failure",
        ),
    )
    executor.max_output_bytes = 24
    target = target_service.list()[0]
    proposal = asyncio.run(executor.propose(target.id, _proposal_request()))

    result = executor.execute(proposal.id)

    assert result.status == "failed"
    assert result.exit_code == 2
    assert result.truncated is True
    assert result.output.endswith("[output truncated]")
    assert executor.get(proposal.id).status == "failed"


def test_ai_diagnostics_reject_non_builtin_target(tmp_path: Path) -> None:
    target_service, executor = _services(tmp_path)
    other = target_service.create(
        RemoteTargetCreate(
            name="Other SSH host",
            transport="ssh",
            host="192.168.50.23",
            port=22,
            username="operator",
            authorization="AUTHORIZED",
        )
    )

    with pytest.raises(DiagnosticError, match="built-in Kali Pi"):
        asyncio.run(executor.propose(other.id, _proposal_request()))


def test_diagnostic_api_requires_approval_and_audits_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_service, executor = _services(tmp_path)
    store = TaskStore(tmp_path / "boxbrain.sqlite3")
    monkeypatch.setattr(api, "remote_target_service", target_service)
    monkeypatch.setattr(api, "diagnostic_executor_service", executor)
    monkeypatch.setattr(api, "task_store", store)
    client = TestClient(create_app())
    target = target_service.list()[0]

    created = client.post(
        f"/api/v1/remote-targets/{target.id}/diagnostic-proposals",
        json={
            "goal": "Check Pi disk space",
            "authorization": "AUTHORIZED",
        },
    )
    assert created.status_code == 201
    proposal_id = created.json()["id"]
    assert created.json()["status"] == "pending"

    invalid = client.post(
        f"/api/v1/diagnostic-proposals/{proposal_id}/execute",
        json={"confirmation": "run"},
    )
    assert invalid.status_code == 422

    executed = client.post(
        f"/api/v1/diagnostic-proposals/{proposal_id}/execute",
        json={"confirmation": "RUN"},
    )
    assert executed.status_code == 200
    assert executed.json()["status"] == "succeeded"

    event_types = [
        item["event_type"] for item in client.get("/api/v1/events").json()
    ]
    assert "diagnostic.proposed" in event_types
    assert "diagnostic.execution_completed" in event_types


def test_emergency_stop_blocks_approved_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command_calls = 0

    def run_command(command: list[str], timeout: float) -> DiagnosticCommandResult:
        nonlocal command_calls
        command_calls += 1
        return DiagnosticCommandResult(exit_code=0, stdout="ok", stderr="")

    target_service, executor = _services(
        tmp_path,
        command_runner=run_command,
    )
    store = TaskStore(tmp_path / "boxbrain.sqlite3")
    monkeypatch.setattr(api, "remote_target_service", target_service)
    monkeypatch.setattr(api, "diagnostic_executor_service", executor)
    monkeypatch.setattr(api, "task_store", store)
    client = TestClient(create_app())
    target = target_service.list()[0]
    proposal = asyncio.run(executor.propose(target.id, _proposal_request()))
    store.engage_emergency_stop(reason="Test stop")

    response = client.post(
        f"/api/v1/diagnostic-proposals/{proposal.id}/execute",
        json={"confirmation": "RUN"},
    )

    assert response.status_code == 423
    assert command_calls == 0
    assert executor.get(proposal.id).status == "pending"