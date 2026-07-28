from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from boxbrain_controller import api
from boxbrain_controller.app import create_app
from boxbrain_controller.models import RemoteSessionRequest, RemoteTargetCreate
from boxbrain_controller.remote_targets import (
    RemoteTargetError,
    RemoteTargetScopeError,
    RemoteTargetService,
)
from boxbrain_controller.task_store import TaskStore


class _Connection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _private_resolver(host: str, port: int) -> list[tuple[Any, ...]]:
    return [
        (
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            ("192.168.50.23", port),
        )
    ]


def _public_resolver(host: str, port: int) -> list[tuple[Any, ...]]:
    return [
        (
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            ("8.8.8.8", port),
        )
    ]


def _create_request(**overrides: object) -> RemoteTargetCreate:
    payload: dict[str, object] = {
        "name": "Repair PC",
        "transport": "ssh",
        "host": "repair-pc.local",
        "port": 22,
        "username": "technician",
        "authorization": "AUTHORIZED",
    }
    payload.update(overrides)
    return RemoteTargetCreate.model_validate(payload)


def test_remote_target_store_seeds_usb_and_probes_private_target(
    tmp_path: Path,
) -> None:
    connections: list[_Connection] = []

    def connector(host: str, port: int, timeout: float) -> _Connection:
        assert host == "repair-pc.local"
        assert port == 22
        assert timeout == 1.5
        connection = _Connection()
        connections.append(connection)
        return connection

    service = RemoteTargetService(
        tmp_path / "targets.sqlite3",
        resolver=_private_resolver,
        connector=connector,
        launcher=lambda command: None,
    )

    built_in = service.list()[0]
    assert built_in.name == "Kali Pi USB-C"
    assert built_in.transport == "usb-c"
    assert built_in.host == "10.12.194.1"
    assert built_in.built_in is True

    created = service.create(_create_request())
    result = service.probe(created.id)

    assert result.status == "online"
    assert result.resolved_address == "192.168.50.23"
    assert connections[0].closed is True
    assert service.get(created.id).status == "online"


def test_duplicate_remote_target_is_rejected_cleanly(tmp_path: Path) -> None:
    service = RemoteTargetService(
        tmp_path / "targets.sqlite3",
        resolver=_private_resolver,
        launcher=lambda command: None,
    )
    service.create(_create_request())

    with pytest.raises(RemoteTargetError, match="already registered"):
        service.create(_create_request(name="Duplicate label"))


@pytest.mark.parametrize(
    ("transport", "port", "username", "expected"),
    [
        (
            "usb-c",
            22,
            "kali",
            ["ssh", "-p", "22", "kali@repair-pc.local"],
        ),
        (
            "winrm",
            5986,
            None,
            [
                "powershell.exe",
                "-NoExit",
                "-NoProfile",
                "-Command",
                "Enter-PSSession -ComputerName 'repair-pc.local' "
                "-Port 5986 -UseSSL",
            ],
        ),
    ],
)
def test_usb_and_winrm_sessions_use_fixed_commands(
    tmp_path: Path,
    transport: str,
    port: int,
    username: str | None,
    expected: list[str],
) -> None:
    launched: list[list[str]] = []
    service = RemoteTargetService(
        tmp_path / "targets.sqlite3",
        resolver=_private_resolver,
        launcher=launched.append,
    )
    target = service.create(
        _create_request(
            transport=transport,
            port=port,
            username=username,
        )
    )

    service.open_session(target.id, RemoteSessionRequest(confirmation="OPEN"))

    assert launched == [expected]

def test_remote_target_scope_and_telnet_safety_are_enforced(
    tmp_path: Path,
) -> None:
    service = RemoteTargetService(
        tmp_path / "targets.sqlite3",
        resolver=_public_resolver,
        launcher=lambda command: None,
    )

    with pytest.raises(RemoteTargetError, match="Telnet is plaintext"):
        service.create(_create_request(transport="telnet", port=23))

    public = service.create(_create_request(host="public.example"))
    with pytest.raises(RemoteTargetScopeError, match="private"):
        service.probe(public.id)


def test_operator_sessions_use_fixed_argv_and_require_telnet_warning(
    tmp_path: Path,
) -> None:
    launched: list[list[str]] = []
    service = RemoteTargetService(
        tmp_path / "targets.sqlite3",
        resolver=_private_resolver,
        connector=lambda host, port, timeout: _Connection(),
        launcher=launched.append,
    )
    ssh = service.create(_create_request())
    result = service.open_session(
        ssh.id,
        RemoteSessionRequest(confirmation="OPEN"),
    )

    assert result.application == "SSH terminal"
    assert launched == [
        ["ssh", "-p", "22", "technician@repair-pc.local"]
    ]

    telnet = service.create(
        _create_request(
            name="Legacy Lab",
            transport="telnet",
            port=23,
            username=None,
            insecure_transport_acknowledged=True,
        )
    )
    with pytest.raises(RemoteTargetError, match="PLAINTEXT"):
        service.open_session(
            telnet.id,
            RemoteSessionRequest(confirmation="OPEN"),
        )
    service.open_session(
        telnet.id,
        RemoteSessionRequest(
            confirmation="OPEN",
            insecure_confirmation="I UNDERSTAND TELNET IS PLAINTEXT",
        ),
    )
    assert launched[-1] == ["telnet.exe", "repair-pc.local", "23"]


def test_remote_target_api_registers_probes_and_opens_audited_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launched: list[list[str]] = []
    service = RemoteTargetService(
        tmp_path / "targets.sqlite3",
        resolver=_private_resolver,
        connector=lambda host, port, timeout: _Connection(),
        launcher=launched.append,
    )
    store = TaskStore(tmp_path / "controller.sqlite3")
    monkeypatch.setattr(api, "remote_target_service", service)
    monkeypatch.setattr(api, "task_store", store)
    client = TestClient(create_app())

    created = client.post(
        "/api/v1/remote-targets",
        json={
            "name": "Repair PC",
            "transport": "rdp",
            "host": "repair-pc.local",
            "port": 3389,
            "authorization": "AUTHORIZED",
        },
    )
    assert created.status_code == 201
    target_id = created.json()["id"]

    probe = client.post(f"/api/v1/remote-targets/{target_id}/probe")
    assert probe.status_code == 200
    assert probe.json()["status"] == "online"

    session = client.post(
        f"/api/v1/remote-targets/{target_id}/session",
        json={"confirmation": "OPEN"},
    )
    assert session.status_code == 200
    assert session.json()["application"] == "RDP"
    assert launched == [["mstsc.exe", "/v:repair-pc.local:3389"]]

    event_types = [item["event_type"] for item in client.get(
        "/api/v1/events"
    ).json()]
    assert "remote_target.registered" in event_types
    assert "remote_target.probed" in event_types
    assert "remote_target.session_opened" in event_types


def test_emergency_stop_blocks_remote_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launched: list[list[str]] = []
    service = RemoteTargetService(
        tmp_path / "targets.sqlite3",
        resolver=_private_resolver,
        launcher=launched.append,
    )
    store = TaskStore(tmp_path / "controller.sqlite3")
    monkeypatch.setattr(api, "remote_target_service", service)
    monkeypatch.setattr(api, "task_store", store)
    client = TestClient(create_app())
    target = service.create(_create_request())
    store.engage_emergency_stop(reason="Test stop")

    response = client.post(
        f"/api/v1/remote-targets/{target.id}/session",
        json={"confirmation": "OPEN"},
    )

    assert response.status_code == 423
    assert launched == []