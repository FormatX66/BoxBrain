import sqlite3

import pytest

from boxbrain_controller.models import TaskCreate
from boxbrain_controller.task_store import TaskStore


def test_tasks_and_events_survive_store_restart(tmp_path) -> None:
    database_path = tmp_path / "boxbrain.sqlite3"
    first_store = TaskStore(database_path)
    task = first_store.create(
        TaskCreate(
            goal="Observe a disposable target",
            target_id="windows-sandbox",
            policy_profile="safe",
        )
    )

    reopened_store = TaskStore(database_path)

    assert reopened_store.get(task.id) == task
    assert reopened_store.list() == [task]
    events = reopened_store.list_events()
    assert len(events) == 1
    assert events[0].event_type == "task.queued"
    assert events[0].task_id == task.id


@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_audit_events_reject_mutation(tmp_path, operation) -> None:
    store = TaskStore(tmp_path / "boxbrain.sqlite3")
    store.create(
        TaskCreate(
            goal="Create immutable evidence",
            target_id="windows-sandbox",
            policy_profile="safe",
        )
    )
    statement = (
        "UPDATE audit_events SET message = 'changed'"
        if operation == "UPDATE"
        else "DELETE FROM audit_events"
    )

    with sqlite3.connect(store.database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(statement)

def test_emergency_stop_state_and_audit_survive_restart(tmp_path) -> None:
    database_path = tmp_path / "boxbrain.sqlite3"
    first_store = TaskStore(database_path)

    engaged = first_store.engage_emergency_stop(reason="Test safety boundary")
    reopened_store = TaskStore(database_path)

    assert engaged.engaged is True
    assert engaged.generation == 1
    assert reopened_store.get_emergency_stop() == engaged

    reset = reopened_store.reset_emergency_stop()
    final_store = TaskStore(database_path)

    assert reset.engaged is False
    assert reset.reason is None
    assert reset.generation == 2
    assert final_store.get_emergency_stop() == reset
    assert [event.event_type for event in final_store.list_events()] == [
        "safety.emergency_stop_reset",
        "safety.emergency_stop_engaged",
    ]
