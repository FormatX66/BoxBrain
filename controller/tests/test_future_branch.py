from dataclasses import replace

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient

from boxbrain_controller import app as app_module


@pytest.fixture
def application(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "settings", replace(app_module.settings,
        data_dir=tmp_path, repository_root=tmp_path, api_token="a" * 32))
    return app_module.create_app()


def client(app):
    return TestClient(app, headers={"X-BoxBrain-Token": "a" * 32}, raise_server_exceptions=False)


def test_failed_action_is_quarantined_across_request_ids_and_app_restart(application):
    calls = []

    async def fail(request: Request):
        calls.append(await request.json())
        return {"status": "failed", "reason": "test proof"}

    application.add_api_route("/api/v1/test-effect", fail, methods=["POST"])
    response = client(application).post("/api/v1/test-effect", json={"value": 1, "request_id": "a"})
    assert response.status_code == 200
    assert response.headers["x-aurum-future-branch-scope"] == "admission_only"
    restarted = app_module.create_app()
    restarted.add_api_route("/api/v1/test-effect", fail, methods=["POST"])
    repeated = client(restarted).post("/api/v1/test-effect", json={"value": 1, "request_id": "b"})
    assert repeated.status_code == 409
    assert repeated.json()["detail"] == "unchanged_failed_operation"
    assert len(calls) == 1
    assert client(restarted).post("/api/v1/test-effect", json={"value": 2}).status_code == 200
    assert len(calls) == 2


def test_authentication_precedes_gate_and_refusal_is_not_quarantined(application):
    @application.post("/api/v1/test-effect")
    def refuse():
        return JSONResponse({"status": "refused"}, status_code=403)

    assert TestClient(application).post("/api/v1/test-effect").status_code == 401
    assert application.state.future_branch.status()["operations"] == {}
    for _ in range(2):
        assert client(application).post("/api/v1/test-effect").status_code == 403
    assert application.state.future_branch.status()["operations"] == {"refused": 1}


def test_exception_is_uncertain_not_safe_to_repeat(application):
    @application.post("/api/v1/crash")
    def crash():
        raise RuntimeError("effect may have happened")

    assert client(application).post("/api/v1/crash").status_code == 500
    assert client(application).post("/api/v1/crash").status_code == 409


def test_streams_preserved_and_reads_can_gather_new_evidence(application):
    @application.get("/api/v1/test-stream")
    def stream():
        return StreamingResponse(iter([b"one", b"two"]), media_type="text/event-stream")

    for _ in range(2):
        response = client(application).get("/api/v1/test-stream")
        assert response.content == b"onetwo"
        assert "x-aurum-future-branch" in response.headers


def test_emergency_stop_survives_journal_failure(application, monkeypatch):
    from boxbrain_controller import api as api_module
    from boxbrain_controller.task_store import TaskStore
    monkeypatch.setattr(api_module, "task_store", TaskStore(app_module.settings.data_dir / "tasks.sqlite3"))
    def unavailable(*args, **kwargs):
        raise OSError("storage unavailable")
    monkeypatch.setattr(application.state.future_branch, "begin", unavailable)
    response = client(application).post("/api/v1/safety/emergency-stop/engage", json={"reason": "test stop"})
    assert response.status_code == 200
    assert response.json()["engaged"]
