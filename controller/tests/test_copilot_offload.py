from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from boxbrain_controller import api
from boxbrain_controller.app import create_app
from boxbrain_controller.copilot_offload import (
    GITHUB_COPILOT_SEND_CONFIRMATION,
    CopilotCommandResult,
    CopilotDispatchRequest,
    CopilotOffloadError,
    CopilotOffloadService,
    CopilotPrepareRequest,
    CopilotProvider,
    CopilotRuntimeUnavailable,
    CopilotTaskKind,
)
from boxbrain_controller.settings import settings


def _service(
    tmp_path: Path,
    *,
    enabled: bool = False,
    installed: bool = False,
    windows_installed: bool = False,
    runner=None,
) -> tuple[CopilotOffloadService, Path]:
    repository = tmp_path / "repo"
    repository.mkdir()
    service = CopilotOffloadService(
        repository,
        tmp_path / "state",
        allowed_roots=(repository,),
        enabled=enabled,
        cli_finder=(
            (lambda _name: "C:\\Program Files\\GitHub Copilot\\copilot.exe")
            if installed
            else (lambda _name: None)
        ),
        windows_app_detector=lambda: windows_installed,
        command_runner=runner or (lambda _command, _cwd, _timeout: None),
    )
    return service, repository


def test_file_organization_packet_contains_metadata_only(tmp_path) -> None:
    service, repository = _service(tmp_path)
    folder = repository / "Downloads"
    folder.mkdir()
    (folder / "notes.txt").write_text("private note body", encoding="utf-8")
    (folder / "photo.jpg").write_bytes(b"not-a-real-photo")
    (folder / ".env").write_text("PASSWORD=not-for-copilot", encoding="utf-8")

    packet = service.prepare(
        CopilotPrepareRequest(
            task_id="BB-008",
            description="Group these files into sensible folders.",
            kind=CopilotTaskKind.FILE_ORGANIZATION,
            paths=("Downloads",),
        )
    )

    assert {item.path for item in packet.files} == {
        "Downloads/notes.txt",
        "Downloads/photo.jpg",
    }
    assert all(item.content_included is False for item in packet.files)
    assert all(item.sha256 is None for item in packet.files)
    assert packet.total_content_bytes == 0
    assert "private note body" not in packet.prompt
    assert "not-a-real-photo" not in packet.prompt
    assert "not-for-copilot" not in packet.prompt
    assert any(item.path.endswith(".env") for item in packet.excluded)
    assert "Do not delete, overwrite, or execute" in packet.prompt


def test_code_packet_is_scoped_and_rejects_credential_material(tmp_path) -> None:
    service, repository = _service(tmp_path)
    source = repository / "plugin"
    source.mkdir()
    (source / "safe.py").write_text(
        "def greeting(name: str) -> str:\n    return f'Hello {name}'\n",
        encoding="utf-8",
    )
    (source / "secret.py").write_text(
        'api_key = "abcdefghijklmno123456"\n',
        encoding="utf-8",
    )
    (source / "binary.exe").write_bytes(b"MZ")

    packet = service.prepare(
        CopilotPrepareRequest(
            task_id="BB-008",
            description="Review the Windows plugin implementation.",
            kind=CopilotTaskKind.PLUGIN_CODE,
            paths=("plugin",),
        )
    )

    assert [item.path for item in packet.files] == ["plugin/safe.py"]
    assert packet.files[0].content_included is True
    assert "def greeting" in packet.prompt
    assert "abcdefghijklmno123456" not in packet.prompt
    reasons = {item.path: item.reason for item in packet.excluded}
    assert reasons["plugin/secret.py"] == "possible credential material"
    assert reasons["plugin/binary.exe"] == "unsupported code file type"

    with pytest.raises(CopilotOffloadError, match="inside the approved root"):
        service.prepare(
            CopilotPrepareRequest(
                description="Escape the selected root.",
                kind=CopilotTaskKind.WINDOWS_CODE,
                paths=("../outside.py",),
            )
        )
    with pytest.raises(CopilotOffloadError, match="High-impact"):
        service.prepare(
            CopilotPrepareRequest(
                description="Change a production plugin.",
                kind=CopilotTaskKind.PLUGIN_CODE,
                paths=("plugin/safe.py",),
                high_impact=True,
            )
        )
    with pytest.raises(CopilotOffloadError, match="objective"):
        service.prepare(
            CopilotPrepareRequest(
                description='Use api_key="abcdefghijklmno123456" for this review.',
                kind=CopilotTaskKind.PLUGIN_CODE,
                paths=("plugin/safe.py",),
            )
        )


def test_dispatch_uses_isolated_plan_mode_and_never_applies_changes(tmp_path) -> None:
    calls: list[tuple[list[str], Path, float]] = []

    def runner(
        command: list[str],
        working_directory: Path,
        timeout_seconds: float,
    ) -> CopilotCommandResult:
        calls.append((command, working_directory, timeout_seconds))
        return CopilotCommandResult(
            exit_code=0,
            stdout="Proposed patch for review only.",
            stderr="",
        )

    service, repository = _service(
        tmp_path,
        enabled=True,
        installed=True,
        runner=runner,
    )
    source = repository / "tool.ps1"
    source.write_text("Get-ChildItem | Select-Object Name\n", encoding="utf-8")
    description = "Improve this local Windows inventory helper."
    packet = service.prepare(
        CopilotPrepareRequest(
            task_id="BB-008",
            description=description,
            kind=CopilotTaskKind.WINDOWS_CODE,
            paths=("tool.ps1",),
        )
    )
    result = service.dispatch(
        CopilotDispatchRequest(
            packet_id=packet.packet_id,
            confirmation=GITHUB_COPILOT_SEND_CONFIRMATION,
        )
    )

    assert result.status == "succeeded"
    assert result.applied_changes is False
    assert result.response == "Proposed patch for review only."
    command, working_directory, timeout = calls[0]
    assert command[0].endswith("copilot.exe")
    assert "--mode=plan" in command
    assert "--available-tools=view" in command
    assert "--allow-tool=read(request.md)" in command
    assert "--no-remote" in command
    assert "--no-remote-export" in command
    assert "--disable-builtin-mcps" in command
    assert "--no-custom-instructions" in command
    assert "--disallow-temp-dir" in command
    assert not any("allow-all" in argument for argument in command)
    assert "--autopilot" not in command
    assert description not in command
    assert timeout == 120.0
    assert working_directory == service.packet_root / str(packet.packet_id)
    assert description in (working_directory / "request.md").read_text(encoding="utf-8")
    assert (working_directory / "response.json").is_file()

    with pytest.raises(CopilotOffloadError, match="already dispatched"):
        service.dispatch(
            CopilotDispatchRequest(
                packet_id=packet.packet_id,
                confirmation=GITHUB_COPILOT_SEND_CONFIRMATION,
            )
        )

    audit = service.events_path.read_text(encoding="utf-8")
    assert description not in audit
    assert "Get-ChildItem" not in audit
    assert "Proposed patch" not in audit


def test_runtime_fails_closed_when_disabled_or_cli_missing(tmp_path) -> None:
    service, repository = _service(tmp_path)
    (repository / "safe.py").write_text("print('safe')\n", encoding="utf-8")
    packet = service.prepare(
        CopilotPrepareRequest(
            description="Review this file.",
            kind=CopilotTaskKind.WINDOWS_CODE,
            paths=("safe.py",),
        )
    )

    runtime = service.runtime_status()
    assert runtime.automated_provider is CopilotProvider.GITHUB_COPILOT_CLI
    assert runtime.dispatch_available is False
    providers = {item.provider: item for item in runtime.providers}
    github = providers[CopilotProvider.GITHUB_COPILOT_CLI]
    windows = providers[CopilotProvider.WINDOWS_COPILOT_APP]
    assert github.display_name == "GitHub Copilot CLI"
    assert github.vendor == "GitHub"
    assert github.installed is False
    assert github.boxbrain_dispatch_enabled is False
    assert github.dispatch_mode == "guarded_automation"
    assert github.dispatch_available is False
    assert github.automated_task_kinds == tuple(CopilotTaskKind)
    assert github.mutation_tools_available is False
    assert windows.display_name == "Microsoft Copilot (Windows app)"
    assert windows.vendor == "Microsoft"
    assert windows.installed is False
    assert windows.dispatch_mode == "manual_only"
    assert windows.dispatch_available is False
    assert windows.automated_task_kinds == ()
    assert windows.mutation_tools_available is False
    with pytest.raises(CopilotRuntimeUnavailable, match="disabled"):
        service.dispatch(
            CopilotDispatchRequest(
                packet_id=packet.packet_id,
                confirmation=GITHUB_COPILOT_SEND_CONFIRMATION,
            )
        )


def test_copilot_api_exposes_runtime_prepare_and_confirmed_dispatch(
    tmp_path, monkeypatch
) -> None:
    def runner(
        _command: list[str],
        _working_directory: Path,
        _timeout_seconds: float,
    ) -> CopilotCommandResult:
        return CopilotCommandResult(exit_code=0, stdout="Review result", stderr="")

    service, repository = _service(
        tmp_path,
        enabled=True,
        installed=True,
        windows_installed=True,
        runner=runner,
    )
    (repository / "plugin.json").write_text(
        json.dumps({"name": "example", "version": "1.0.0"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(api, "copilot_offload_service", service)
    headers = (
        {"X-BoxBrain-Token": settings.api_token}
        if settings.api_token is not None
        else {}
    )

    with TestClient(create_app(), headers=headers) as client:
        runtime = client.get("/api/v1/processing/copilot/runtime")
        assert runtime.status_code == 200
        assert runtime.json()["dispatch_available"] is True
        assert runtime.json()["automated_provider"] == "github-copilot-cli"
        runtime_providers = {
            item["provider"]: item for item in runtime.json()["providers"]
        }
        assert runtime_providers["github-copilot-cli"]["vendor"] == "GitHub"
        assert runtime_providers["github-copilot-cli"]["dispatch_available"] is True
        assert runtime_providers["windows-copilot-app"]["vendor"] == "Microsoft"
        assert runtime_providers["windows-copilot-app"]["installed"] is True
        assert runtime_providers["windows-copilot-app"]["dispatch_mode"] == "manual_only"
        assert runtime_providers["windows-copilot-app"]["dispatch_available"] is False

        providers = client.get("/api/v1/processing/copilot/providers")
        assert providers.status_code == 200
        assert [item["provider"] for item in providers.json()] == [
            "github-copilot-cli",
            "windows-copilot-app",
        ]

        prepared = client.post(
            "/api/v1/processing/copilot/packets",
            json={
                "task_id": "BB-008",
                "description": "Review the plugin manifest.",
                "kind": "plugin_code",
                "paths": ["plugin.json"],
            },
        )
        assert prepared.status_code == 200
        packet_id = prepared.json()["packet_id"]
        assert (
            prepared.json()["confirmation_phrase"]
            == GITHUB_COPILOT_SEND_CONFIRMATION
        )
        assert prepared.json()["provider"] == "github-copilot-cli"

        rejected = client.post(
            "/api/v1/processing/copilot/dispatches",
            json={"packet_id": packet_id, "confirmation": "SEND TO COPILOT"},
        )
        assert rejected.status_code == 422

        dispatched = client.post(
            "/api/v1/processing/copilot/dispatches",
            json={
                "packet_id": packet_id,
                "confirmation": GITHUB_COPILOT_SEND_CONFIRMATION,
            },
        )
        assert dispatched.status_code == 200
        assert dispatched.json()["response"] == "Review result"
        assert dispatched.json()["applied_changes"] is False
