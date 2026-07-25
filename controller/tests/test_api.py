from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from boxbrain_controller import api as api_module
from boxbrain_controller import app as app_module
from boxbrain_controller.app import create_app
from boxbrain_controller.sandbox_observer import SandboxNotRunningError
from boxbrain_controller.task_store import TaskStore


client = TestClient(create_app())


@pytest.fixture(autouse=True)
def isolated_task_store(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        api_module,
        "task_store",
        TaskStore(tmp_path / "boxbrain-test.sqlite3"),
    )


def test_local_api_token_protects_controller_routes(monkeypatch) -> None:
    token = "a" * 32
    monkeypatch.setattr(
        app_module,
        "settings",
        replace(app_module.settings, api_token=token),
    )
    protected_client = TestClient(app_module.create_app())

    health = protected_client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["authentication_required"] is True
    assert health.json()["event_stream_enabled"] is True

    missing = protected_client.get(
        "/api/v1/targets",
        headers={"Origin": "http://127.0.0.1:8080"},
    )
    assert missing.status_code == 401
    assert missing.json()["detail"] == "A valid BoxBrain API token is required."
    assert missing.headers["access-control-allow-origin"] == (
        "http://127.0.0.1:8080"
    )
    assert missing.headers["cache-control"] == "no-store"
    assert missing.headers["x-content-type-options"] == "nosniff"
    assert missing.headers["x-frame-options"] == "DENY"

    assert protected_client.get(
        "/api/v1/targets",
        headers={"X-BoxBrain-Token": "wrong"},
    ).status_code == 401
    assert protected_client.get(
        "/api/v1/targets",
        headers={"X-BoxBrain-Token": token},
    ).status_code == 200
    openapi = protected_client.get("/openapi.json").json()
    assert openapi["components"]["securitySchemes"]["BoxBrainToken"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-BoxBrain-Token",
    }
    assert openapi["paths"]["/api/v1/health"]["get"]["security"] == []


def test_short_api_token_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(
        app_module,
        "settings",
        replace(app_module.settings, api_token="too-short"),
    )

    with pytest.raises(ValueError, match="at least 32 characters"):
        app_module.create_app()


def test_health_reports_executor_disabled() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["executor_enabled"] is False
    assert response.json()["authentication_required"] is False
    assert response.json()["event_stream_enabled"] is True
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-security-policy"].startswith(
        "default-src 'none'"
    )


def test_untrusted_host_is_rejected() -> None:
    response = client.get(
        "/api/v1/health",
        headers={"Host": "attacker.example"},
    )

    assert response.status_code == 400


def test_task_can_be_queued_but_is_not_executed() -> None:
    response = client.post(
        "/api/v1/tasks",
        json={
            "goal": "Open the calculator in the disposable test VM",
            "target_id": "windows-sandbox",
            "policy_profile": "safe",
        },
    )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["target_id"] == "windows-sandbox"
    assert client.get("/api/v1/health").json()["executor_enabled"] is False


def test_unknown_target_is_rejected_before_queueing() -> None:
    response = client.post(
        "/api/v1/tasks",
        json={
            "goal": "Do not run this",
            "target_id": "not-allowlisted",
            "policy_profile": "safe",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Target is not allowlisted."
    assert client.get("/api/v1/tasks").json() == []
    assert client.get("/api/v1/events").json() == []


def test_queueing_task_appends_audit_event() -> None:
    task = client.post(
        "/api/v1/tasks",
        json={
            "goal": "Observe the calculator window",
            "target_id": "windows-sandbox",
            "policy_profile": "safe",
        },
    ).json()

    response = client.get("/api/v1/events")

    assert response.status_code == 200
    event = response.json()[0]
    assert event["sequence"] == 1
    assert event["event_type"] == "task.queued"
    assert event["task_id"] == task["id"]
    assert event["target_id"] == "windows-sandbox"
    assert event["details"]["status"] == "queued"


def test_event_stream_rejects_invalid_resume_sequence() -> None:
    response = client.get(
        "/api/v1/events/stream",
        headers={"Last-Event-ID": "not-a-sequence"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Last-Event-ID must be an audit sequence number."
    )

def test_policy_profiles_keep_lab_invariants() -> None:
    response = client.get("/api/v1/policies")

    assert response.status_code == 200
    profiles = response.json()
    assert {profile["name"] for profile in profiles} == {
        "safe",
        "research",
        "open",
    }
    assert all(profile["immutable_audit_log"] for profile in profiles)
    assert all(profile["isolated_target_required"] for profile in profiles)


def test_local_web_dashboard_origin_is_allowed() -> None:
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://127.0.0.1:8080",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "http://127.0.0.1:8080"
    )


def test_enabled_observer_plugin_declares_only_read_capabilities() -> None:
    response = client.get("/api/v1/plugins")

    assert response.status_code == 200
    observer = next(
        plugin
        for plugin in response.json()
        if plugin["id"] == "boxbrain.windows-sandbox-observer"
    )
    assert observer["enabled"] is True
    assert observer["protocol_version"] == "1"
    assert observer["process_boundary"] == "out-of-process"
    assert observer["target_id"] == "windows-sandbox"
    assert observer["capabilities"] == [
        "observation.describe",
        "observation.frame",
    ]
    assert all("input" not in item for item in observer["capabilities"])


def test_sandbox_target_is_strictly_read_only() -> None:
    response = client.get("/api/v1/targets")

    assert response.status_code == 200
    target = response.json()[0]
    assert target["id"] == "windows-sandbox"
    assert target["transport"] == "out-of-process-plugin"
    assert target["mode"] == "read-only"
    assert target["input_enabled"] is False
    assert target["observer_plugin_id"] == (
        "boxbrain.windows-sandbox-observer"
    )
    assert target["observer_process_boundary"] == "out-of-process"
    assert target["observation_status"] == "ready"
    assert client.post(
        "/api/v1/targets/windows-sandbox/input",
        json={"type": "keyboard", "value": "test"},
    ).status_code == 404


def test_sandbox_start_is_fixed_profile_only_and_audited(monkeypatch) -> None:
    calls = []

    def start() -> str:
        calls.append("configured-profile")
        return "starting"

    monkeypatch.setattr(api_module.sandbox_observer, "start", start)

    response = client.post(
        "/api/v1/targets/windows-sandbox/start",
        json={"profile_path": "C:/untrusted/other.wsb"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "target_id": "windows-sandbox",
        "status": "starting",
        "message": "Windows Sandbox launch requested.",
    }
    assert calls == ["configured-profile"]
    events = client.get("/api/v1/events").json()
    assert len(events) == 1
    assert events[0]["event_type"] == "target.start_requested"
    assert events[0]["details"] == {"result": "starting"}

def test_emergency_stop_blocks_launch_until_confirmed_reset(monkeypatch) -> None:
    calls = []

    def start() -> str:
        calls.append("configured-profile")
        return "starting"

    monkeypatch.setattr(api_module.sandbox_observer, "start", start)

    initial = client.get("/api/v1/safety/emergency-stop")
    assert initial.status_code == 200
    assert initial.json()["engaged"] is False
    assert initial.json()["generation"] == 0

    engaged = client.post(
        "/api/v1/safety/emergency-stop/engage",
        json={"reason": "Operator safety test"},
    )
    assert engaged.status_code == 200
    assert engaged.json()["engaged"] is True
    assert engaged.json()["reason"] == "Operator safety test"
    assert engaged.json()["generation"] == 1

    target = client.get("/api/v1/targets").json()[0]
    assert target["start_enabled"] is False
    assert target["start_endpoint"] is None

    blocked = client.post("/api/v1/targets/windows-sandbox/start", json={})
    assert blocked.status_code == 423
    assert blocked.json()["detail"].startswith("Emergency stop is engaged")
    assert calls == []

    invalid_reset = client.post(
        "/api/v1/safety/emergency-stop/reset",
        json={"confirmation": "reset"},
    )
    assert invalid_reset.status_code == 422
    assert client.get("/api/v1/safety/emergency-stop").json()["engaged"] is True

    reset = client.post(
        "/api/v1/safety/emergency-stop/reset",
        json={"confirmation": "RESET"},
    )
    assert reset.status_code == 200
    assert reset.json()["engaged"] is False
    assert reset.json()["reason"] is None
    assert reset.json()["generation"] == 2

    launched = client.post("/api/v1/targets/windows-sandbox/start", json={})
    assert launched.status_code == 200
    assert calls == ["configured-profile"]

    events = client.get("/api/v1/events").json()
    assert [event["event_type"] for event in events] == [
        "target.start_requested",
        "safety.emergency_stop_reset",
        "target.start_requested",
        "safety.emergency_stop_engaged",
    ]
    assert events[2]["details"]["result"] == "blocked"

def test_sandbox_frame_has_no_store_and_read_only_headers(monkeypatch) -> None:
    monkeypatch.setattr(
        api_module.sandbox_observer,
        "capture_png",
        lambda: b"\x89PNG\r\n\x1a\nframe",
    )

    response = client.get("/api/v1/targets/windows-sandbox/frame")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.headers["x-boxbrain-capture-mode"] == "read-only"


def test_sandbox_frame_reports_disconnected_target(monkeypatch) -> None:
    def not_running() -> bytes:
        raise SandboxNotRunningError("Windows Sandbox is not running.")

    monkeypatch.setattr(
        api_module.sandbox_observer,
        "capture_png",
        not_running,
    )

    response = client.get("/api/v1/targets/windows-sandbox/frame")

    assert response.status_code == 404
    assert response.json()["detail"] == "Windows Sandbox is not running."
