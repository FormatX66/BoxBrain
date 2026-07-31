from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from boxbrain_controller import api
from boxbrain_controller.app import create_app
from boxbrain_controller.architecture_manifest import get_architecture_manifest
from boxbrain_controller.fleet import (
    FleetError,
    FleetMachineCreate,
    FleetService,
    ProvisioningStepCompleteRequest,
)
from boxbrain_controller.models import RemoteTargetCreate
from boxbrain_controller.remote_targets import RemoteTargetService
from boxbrain_controller.task_store import TaskStore


def test_v1_architecture_preserves_processing_and_execution_boundaries() -> None:
    manifest = get_architecture_manifest()

    assert manifest.version == "1.1"
    assert len(manifest.agents) == 12
    assert manifest.flow[0] == "Bruce (User)"
    assert manifest.flow[-1].startswith("Authorized Machine")
    assert {agent.id for agent in manifest.agents} >= {
        "orchestrator",
        "machine-provisioning-agent",
        "brain-connect",
        "capability-registry",
    }
    assert any(
        "existing ten-agent processing crew" in note
        for note in manifest.compatibility_notes
    )


def test_fleet_import_and_provisioning_are_durable_and_ordered(
    tmp_path: Path,
) -> None:
    database = tmp_path / "boxbrain.sqlite3"
    targets = RemoteTargetService(database)
    service = FleetService(database)

    machines = service.import_remote_targets(targets.list())

    assert len(machines) == 1
    machine = machines[0]
    assert machine.kind == "raspberry-pi"
    assert machine.machine_identity.startswith("BB-RPI-")
    assert "edge-diagnostics" in machine.capabilities

    run = service.start_provisioning(machine.id)

    assert run.status == "in_progress"
    assert run.current_step_id == "open-google-signup"
    assert len(run.steps) == 16
    assert run.steps[0].status == "completed"
    assert next(
        step for step in run.steps if step.id == "register-brain-connect"
    ).status == "completed"

    with pytest.raises(FleetError, match="current provisioning step"):
        service.complete_step(
            run.id,
            "configure-github",
            ProvisioningStepCompleteRequest(
                confirmation="COMPLETE",
                note="Out of order.",
            ),
        )

    while run.current_step_id is not None:
        run = service.complete_step(
            run.id,
            run.current_step_id,
            ProvisioningStepCompleteRequest(
                confirmation="COMPLETE",
                note="Verified by operator.",
            ),
        )

    assert run.status == "completed"
    assert service.get(machine.id).status == "ready"
    reloaded = FleetService(database).get_run(run.id)
    assert reloaded.status == "completed"


def test_non_builtin_usb_target_is_a_workstation_and_repairs_old_import(
    tmp_path: Path,
) -> None:
    database = tmp_path / "boxbrain.sqlite3"
    targets = RemoteTargetService(database)
    laptop_target = targets.create(
        RemoteTargetCreate(
            name="HeX Laptop",
            transport="usb-c",
            host="127.0.0.1",
            port=22,
            username="bruce",
            authorization="AUTHORIZED",
        )
    )
    service = FleetService(database)
    old_import = service.create(
        FleetMachineCreate(
            name="HeX Laptop",
            kind="raspberry-pi",
            remote_target_id=laptop_target.id,
            capabilities=list(laptop_target.capabilities),
            authorization="AUTHORIZED",
        )
    )
    assert old_import.machine_identity.startswith("BB-RPI-")

    imported = service.import_remote_targets(targets.list())
    laptop = next(machine for machine in imported if machine.name == "HeX Laptop")

    assert laptop.kind == "workstation"
    assert laptop.machine_identity.startswith("BB-WS-")


def test_fleet_api_imports_target_and_audits_provisioning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "boxbrain.sqlite3"
    targets = RemoteTargetService(database)
    fleet = FleetService(database)
    store = TaskStore(database)
    monkeypatch.setattr(api, "remote_target_service", targets)
    monkeypatch.setattr(api, "fleet_service", fleet)
    monkeypatch.setattr(api, "task_store", store)
    client = TestClient(create_app())

    architecture = client.get("/api/v1/architecture")
    assert architecture.status_code == 200
    assert architecture.json()["version"] == "1.1"
    assert len(client.get("/api/v1/system-agents").json()) == 12

    imported = client.post(
        "/api/v1/fleet/import-targets",
        json={"confirmation": "IMPORT"},
    )
    assert imported.status_code == 200
    machine_id = imported.json()[0]["id"]
    assert client.get("/api/v1/fleet").json()["machine_count"] == 1

    started = client.post(
        f"/api/v1/fleet/machines/{machine_id}/provisioning",
        json={"confirmation": "PROVISION"},
    )
    assert started.status_code == 201
    assert started.json()["current_step_id"] == "open-google-signup"

    completed = client.post(
        (
            f"/api/v1/provisioning/{started.json()['id']}/steps/"
            "open-google-signup/complete"
        ),
        json={
            "confirmation": "COMPLETE",
            "note": "Browser opened by operator.",
        },
    )
    assert completed.status_code == 200
    assert completed.json()["current_step_id"] == "complete-captcha"

    event_types = {
        item["event_type"] for item in client.get("/api/v1/events").json()
    }
    assert {
        "fleet.targets_imported",
        "provisioning.started",
        "provisioning.step_completed",
    } <= event_types
