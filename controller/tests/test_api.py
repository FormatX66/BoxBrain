from fastapi.testclient import TestClient

from boxbrain_controller import api as api_module
from boxbrain_controller.app import create_app


client = TestClient(create_app())


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
            "target_id": "lab-vm-01",
            "policy_profile": "safe",
        },
    )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["target_id"] == "lab-vm-01"


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
