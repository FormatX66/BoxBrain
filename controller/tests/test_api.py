import pytest
from fastapi.testclient import TestClient

from boxbrain_controller import api as api_module
from boxbrain_controller.app import create_app
from boxbrain_controller.task_store import TaskStore


client = TestClient(create_app())


@pytest.fixture(autouse=True)
def isolated_task_store(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        api_module,
        "task_store",
        TaskStore(tmp_path / "boxbrain-test.sqlite3"),
    )


def test_health_reports_executor_disabled() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["executor_enabled"] is False


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


def test_sandbox_target_is_strictly_read_only() -> None:
    response = client.get("/api/v1/targets")

    assert response.status_code == 200
    target = response.json()[0]
    assert target["id"] == "windows-sandbox"
    assert target["mode"] == "read-only"
    assert target["input_enabled"] is False
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

def test_sandbox_frame_has_no_store_and_read_only_headers(monkeypatch) -> None:
    monkeypatch.setattr(
        api_module.sandbox_observer,
        "find_window",
        lambda: object(),
    )
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
