from collections import OrderedDict
from datetime import UTC, datetime
from threading import Lock
from uuid import UUID, uuid4

from .models import TaskCreate, TaskRecord, TaskStatus


class TaskStore:
    """Small in-memory queue used until persistence is designed."""

    def __init__(self) -> None:
        self._items: OrderedDict[UUID, TaskRecord] = OrderedDict()
        self._lock = Lock()

    def create(self, request: TaskCreate) -> TaskRecord:
        record = TaskRecord(
            id=uuid4(),
            goal=request.goal,
            target_id=request.target_id,
            policy_profile=request.policy_profile,
            status=TaskStatus.QUEUED,
            created_at=datetime.now(UTC),
        )
        with self._lock:
            self._items[record.id] = record
        return record

    def list(self) -> list[TaskRecord]:
        with self._lock:
            return list(reversed(self._items.values()))

    def get(self, task_id: UUID) -> TaskRecord | None:
        with self._lock:
            return self._items.get(task_id)

