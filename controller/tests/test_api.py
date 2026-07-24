from fastapi.testclient import TestClient

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

