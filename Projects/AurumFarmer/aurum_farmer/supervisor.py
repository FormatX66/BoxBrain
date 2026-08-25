"""Persistent supervisor/watchdog for Farmer jobs."""
from __future__ import annotations

import hashlib
import socket
import threading
import time
import traceback
import uuid
from typing import Any, Mapping

from .executors import ExecutorRegistry
from .ledger import Ledger
from .models import ExecutionResult, Outcome


class Supervisor:
    """Single-leader scheduler that survives chat and process boundaries."""

    def __init__(
        self,
        ledger: Ledger,
        executors: ExecutorRegistry,
        *,
        name: str = "aurum-farmer-primary",
        owner: str | None = None,
        lease_seconds: float = 90.0,
        poll_seconds: float = 2.0,
    ) -> None:
        self.ledger = ledger
        self.executors = executors
        self.name = name
        self.owner = owner or f"{socket.gethostname()}:{uuid.uuid4().hex[:12]}"
        self.lease_seconds = max(lease_seconds, 10.0)
        self.poll_seconds = max(poll_seconds, 0.1)
        self.stop_event = threading.Event()
        self.last_error: str | None = None
        self.last_tick_at: float | None = None

    def stop(self) -> None:
        self.stop_event.set()

    def _heartbeat_worker(self, attempt_id: str, stop: threading.Event) -> None:
        interval = max(self.lease_seconds / 3.0, 1.0)
        while not stop.wait(interval):
            self.ledger.supervisor_heartbeat(self.name, self.owner, lease_seconds=self.lease_seconds)
            if not self.ledger.heartbeat_attempt(attempt_id, self.owner, lease_seconds=self.lease_seconds):
                return

    def tick(self) -> dict[str, Any]:
        """Run one watchdog/schedule/execute/verify cycle."""
        self.last_tick_at = time.time()
        if not self.ledger.supervisor_heartbeat(self.name, self.owner, lease_seconds=self.lease_seconds):
            return {"status": "standby", "reason": "another healthy supervisor owns the lease"}
        recovered = self.ledger.recover_stale_attempts()
        context = self.ledger.claim_next(self.owner, lease_seconds=self.lease_seconds)
        if context is None:
            return {"status": "idle", "recovered_jobs": recovered}
        attempt_id = context["id"]
        heartbeat_stop = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat_worker,
            args=(attempt_id, heartbeat_stop),
            name=f"farmer-heartbeat-{attempt_id[-8:]}",
            daemon=True,
        )
        heartbeat.start()
        try:
            try:
                executor = self.executors.get(context["executor"])
                result = executor.execute(context)
            except Exception as error:  # executor isolation boundary
                detail = "".join(traceback.format_exception_only(type(error), error)).strip()
                result = ExecutionResult(
                    outcome=Outcome.FAILED,
                    summary=f"Executor raised an isolated exception: {detail}",
                    failure_class="implementation",
                    failure_fingerprint=hashlib.sha256(detail.encode("utf-8")).hexdigest(),
                )
            job = self.ledger.finish_attempt(attempt_id, self.owner, result)
            self.last_error = None
            return {
                "status": "processed",
                "job_id": context["job_id"],
                "attempt_id": attempt_id,
                "job_state": job["state"],
                "outcome": result.outcome.value,
                "recovered_jobs": recovered,
            }
        finally:
            heartbeat_stop.set()
            heartbeat.join(timeout=2)

    def run_forever(self) -> None:
        """Keep supervising until the process receives an explicit stop."""
        while not self.stop_event.is_set():
            try:
                result = self.tick()
                delay = self.poll_seconds if result["status"] in {"idle", "standby"} else 0.05
            except Exception as error:  # keep the watchdog alive and try after bounded delay
                self.last_error = "".join(traceback.format_exception_only(type(error), error)).strip()
                delay = min(max(self.poll_seconds * 2, 1.0), 30.0)
            self.stop_event.wait(delay)
