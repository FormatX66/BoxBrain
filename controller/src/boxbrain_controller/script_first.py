from __future__ import annotations

import difflib
import hashlib
import json
import re
import time
from collections import Counter
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from threading import Lock
from typing import Callable, Literal

from pydantic import BaseModel, Field, field_validator


class TaskRoute(StrEnum):
    SCRIPT = "script"
    GPT = "gpt"
    HYBRID = "hybrid"


class RouteRequest(BaseModel):
    task_id: str | None = Field(default=None, pattern=r"^BB-\d{3}$")
    description: str = Field(min_length=1, max_length=4_000)
    script_id: str | None = Field(default=None, max_length=120)
    deterministic: bool = False
    repetitive: bool = False
    data_heavy: bool = False
    ambiguous: bool = False
    requires_reasoning: bool = False
    high_impact: bool = False
    destructive: bool = False
    model_lane: str | None = Field(default=None, max_length=80)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        return " ".join(value.split())


class RouteDecision(BaseModel):
    route: TaskRoute
    confidence: float = Field(ge=0, le=1)
    reasons: tuple[str, ...]
    fallback: TaskRoute
    human_review_required: bool
    script_available: bool
    queue_state: Literal["active", "complete", "unknown"]
    model_lane: str | None = None


class ScriptSpec(BaseModel):
    id: str
    version: str
    description: str
    input_contract: dict[str, str]
    output_contract: dict[str, str]
    permissions: tuple[str, ...]
    impact: Literal["read-only", "write", "destructive"]
    idempotent: bool
    rollback: str


class ScriptRunRequest(BaseModel):
    task_id: str | None = Field(default=None, pattern=r"^BB-\d{3}$")
    script_id: str = Field(min_length=1, max_length=120)
    version: str | None = Field(default=None, max_length=40)
    payload: dict[str, object] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1, max_length=200)
    confirmation: Literal["APPROVE HIGH IMPACT"] | None = None


class ScriptRunResult(BaseModel):
    task_id: str | None
    script_id: str
    version: str
    route: TaskRoute
    status: Literal["succeeded", "duplicate", "escalated", "rejected"]
    reason: str
    data: dict[str, object]
    duration_ms: float = Field(ge=0)
    avoided_model_call: bool
    idempotency_key: str
    fallback: TaskRoute | None = None


class RoutingMetrics(BaseModel):
    total_decisions: int
    routes: dict[str, int]
    script_runs: int
    successful_script_runs: int
    avoided_model_calls: int
    duplicate_runs_prevented: int
    escalations: int
    reliability_percent: float
    error_rate_percent: float
    average_script_duration_ms: float


ScriptHandler = Callable[[dict[str, object]], dict[str, object]]


class ScriptFirstService:
    """Deterministic task routing and bounded local script execution.

    The service never calls a model or shell. It records route decisions and
    returns explicit escalation results when local execution cannot safely
    finish the work.
    """

    def __init__(self, repository_root: Path, state_dir: Path) -> None:
        self.repository_root = repository_root.resolve()
        self.state_dir = state_dir.resolve()
        self.events_path = self.state_dir / "script-first-events.jsonl"
        self._lock = Lock()
        self._registry: dict[str, tuple[ScriptSpec, ScriptHandler]] = {}
        self._register_builtins()

    def list_scripts(self) -> list[ScriptSpec]:
        return [entry[0] for entry in self._registry.values()]

    def classify(self, request: RouteRequest) -> RouteDecision:
        script_available = request.script_id in self._registry
        queue_state = self._queue_state(request.task_id)
        reasons: list[str] = []

        if request.destructive or request.high_impact:
            route = TaskRoute.HYBRID
            confidence = 1.0
            fallback = TaskRoute.GPT
            reasons.append("High-impact work requires local controls and human review.")
        elif request.ambiguous or request.requires_reasoning:
            route = TaskRoute.GPT
            confidence = 0.95
            fallback = TaskRoute.HYBRID
            reasons.append("Ambiguity or adaptive reasoning requires a model lane.")
        elif script_available and (
            request.deterministic or request.repetitive or request.data_heavy
        ):
            route = TaskRoute.SCRIPT
            confidence = 0.98
            fallback = TaskRoute.HYBRID
            reasons.append("A versioned local script covers the deterministic path.")
        elif request.deterministic or request.repetitive or request.data_heavy:
            route = TaskRoute.HYBRID
            confidence = 0.86
            fallback = TaskRoute.GPT
            reasons.append("Local preprocessing is suitable, but no requested script is registered.")
        else:
            route = TaskRoute.GPT
            confidence = 0.72
            fallback = TaskRoute.HYBRID
            reasons.append("No stable deterministic procedure was declared.")

        if queue_state == "complete":
            reasons.append("Cue Complete already records this task; verify before repeating work.")

        decision = RouteDecision(
            route=route,
            confidence=confidence,
            reasons=tuple(reasons),
            fallback=fallback,
            human_review_required=request.high_impact or request.destructive,
            script_available=script_available,
            queue_state=queue_state,
            model_lane=request.model_lane,
        )
        self._append_event(
            {
                "event": "route_decision",
                "task_id": request.task_id,
                "route": route.value,
                "confidence": confidence,
                "reasons": reasons,
                "model_lane": request.model_lane,
            }
        )
        return decision

    def execute(self, request: ScriptRunRequest) -> ScriptRunResult:
        started = time.perf_counter()
        entry = self._registry.get(request.script_id)
        if entry is None:
            return self._result(
                request,
                version=request.version or "unknown",
                status="escalated",
                reason="Script is not registered; GPT must plan or implement the missing procedure.",
                data={},
                started=started,
                fallback=TaskRoute.GPT,
            )

        spec, handler = entry
        if request.version is not None and request.version != spec.version:
            return self._result(
                request,
                version=spec.version,
                status="rejected",
                reason="Requested script version does not match the registered version.",
                data={"requested_version": request.version},
                started=started,
            )
        if spec.impact != "read-only" and request.confirmation != "APPROVE HIGH IMPACT":
            return self._result(
                request,
                version=spec.version,
                status="rejected",
                reason="A write-capable script requires exact human confirmation.",
                data={},
                started=started,
            )
        if self._queue_state(request.task_id) == "complete":
            return self._result(
                request,
                version=spec.version,
                status="duplicate",
                reason="Cue Complete records this task; duplicate execution was prevented.",
                data={},
                started=started,
            )
        previous = self._successful_run(request.idempotency_key)
        if previous is not None:
            return self._result(
                request,
                version=spec.version,
                status="duplicate",
                reason="The idempotency key already has a successful run.",
                data={"original_timestamp": previous.get("timestamp")},
                started=started,
            )

        try:
            data = handler(request.payload)
        except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as error:
            return self._result(
                request,
                version=spec.version,
                status="escalated",
                reason="Local execution raised a bounded exception; compact evidence is ready for GPT review.",
                data={"error_type": type(error).__name__, "error": str(error)[:500]},
                started=started,
                fallback=TaskRoute.GPT,
            )

        return self._result(
            request,
            version=spec.version,
            status="succeeded",
            reason="The registered local script completed without model involvement.",
            data=data,
            started=started,
        )

    def metrics(self) -> RoutingMetrics:
        events = self._events()
        decisions = [event for event in events if event.get("event") == "route_decision"]
        runs = [event for event in events if event.get("event") == "script_run"]
        successful = [event for event in runs if event.get("status") == "succeeded"]
        failures = [event for event in runs if event.get("status") in {"escalated", "rejected"}]
        durations = [float(event.get("duration_ms", 0)) for event in runs]
        route_counts = Counter(str(event.get("route")) for event in decisions)
        run_count = len(runs)
        return RoutingMetrics(
            total_decisions=len(decisions),
            routes=dict(route_counts),
            script_runs=run_count,
            successful_script_runs=len(successful),
            avoided_model_calls=sum(bool(event.get("avoided_model_call")) for event in runs),
            duplicate_runs_prevented=sum(event.get("status") == "duplicate" for event in runs),
            escalations=sum(event.get("status") == "escalated" for event in runs),
            reliability_percent=round(100 * len(successful) / run_count, 2) if run_count else 0,
            error_rate_percent=round(100 * len(failures) / run_count, 2) if run_count else 0,
            average_script_duration_ms=round(sum(durations) / run_count, 3) if run_count else 0,
        )

    def _register_builtins(self) -> None:
        self._register(
            ScriptSpec(
                id="text.summary",
                version="1.0.0",
                description="Compact large text into deterministic counts and bounded excerpts.",
                input_contract={"text": "string"},
                output_contract={"counts": "object", "head": "string", "tail": "string"},
                permissions=("memory:read",),
                impact="read-only",
                idempotent=True,
                rollback="No rollback required; the script is read-only.",
            ),
            self._text_summary,
        )
        self._register(
            ScriptSpec(
                id="jsonl.summary",
                version="1.0.0",
                description="Validate JSONL and report keys, record counts, and bounded errors.",
                input_contract={"text": "JSONL string"},
                output_contract={"records": "integer", "keys": "object", "errors": "array"},
                permissions=("memory:read",),
                impact="read-only",
                idempotent=True,
                rollback="No rollback required; the script is read-only.",
            ),
            self._jsonl_summary,
        )
        self._register(
            ScriptSpec(
                id="text.diff",
                version="1.0.0",
                description="Produce a bounded unified diff and deterministic change counts.",
                input_contract={"before": "string", "after": "string"},
                output_contract={"added": "integer", "removed": "integer", "diff": "array"},
                permissions=("memory:read",),
                impact="read-only",
                idempotent=True,
                rollback="No rollback required; the script is read-only.",
            ),
            self._text_diff,
        )
        self._register(
            ScriptSpec(
                id="files.inventory",
                version="1.0.0",
                description="Inventory and hash a bounded repository-relative file set.",
                input_contract={"path": "repository-relative string", "max_files": "integer <= 1000"},
                output_contract={"files": "array", "truncated": "boolean", "total_bytes": "integer"},
                permissions=("repository:read",),
                impact="read-only",
                idempotent=True,
                rollback="No rollback required; the script is read-only.",
            ),
            self._files_inventory,
        )

    def _register(self, spec: ScriptSpec, handler: ScriptHandler) -> None:
        self._registry[spec.id] = (spec, handler)

    @staticmethod
    def _text_summary(payload: dict[str, object]) -> dict[str, object]:
        text = payload["text"]
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        lines = text.splitlines()
        return {
            "counts": {
                "characters": len(text),
                "bytes_utf8": len(text.encode("utf-8")),
                "lines": len(lines),
                "nonempty_lines": sum(bool(line.strip()) for line in lines),
                "words": len(text.split()),
            },
            "head": "\n".join(lines[:5])[:1000],
            "tail": "\n".join(lines[-5:])[-1000:],
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }

    @staticmethod
    def _jsonl_summary(payload: dict[str, object]) -> dict[str, object]:
        text = payload["text"]
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        records = 0
        keys: Counter[str] = Counter()
        errors: list[dict[str, object]] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("record is not an object")
                records += 1
                keys.update(value)
            except (json.JSONDecodeError, ValueError) as error:
                if len(errors) < 10:
                    errors.append({"line": line_number, "error": str(error)[:200]})
        return {"records": records, "keys": dict(keys), "errors": errors}

    @staticmethod
    def _text_diff(payload: dict[str, object]) -> dict[str, object]:
        before = payload["before"]
        after = payload["after"]
        if not isinstance(before, str) or not isinstance(after, str):
            raise TypeError("before and after must be strings")
        diff = list(
            difflib.unified_diff(
                before.splitlines(), after.splitlines(), fromfile="before", tofile="after", lineterm=""
            )
        )
        return {
            "added": sum(line.startswith("+") and not line.startswith("+++") for line in diff),
            "removed": sum(line.startswith("-") and not line.startswith("---") for line in diff),
            "diff": diff[:500],
            "truncated": len(diff) > 500,
        }

    def _files_inventory(self, payload: dict[str, object]) -> dict[str, object]:
        relative = payload.get("path", ".")
        max_files = payload.get("max_files", 250)
        if not isinstance(relative, str) or not isinstance(max_files, int):
            raise TypeError("path must be a string and max_files must be an integer")
        if not 1 <= max_files <= 1000:
            raise ValueError("max_files must be between 1 and 1000")
        root = (self.repository_root / relative).resolve()
        if root != self.repository_root and self.repository_root not in root.parents:
            raise ValueError("path must remain inside the repository")
        candidates = [root] if root.is_file() else sorted(path for path in root.rglob("*") if path.is_file())
        files: list[dict[str, object]] = []
        for path in candidates[:max_files]:
            resolved = path.resolve()
            if self.repository_root not in resolved.parents and resolved != self.repository_root:
                continue
            content = resolved.read_bytes()
            files.append(
                {
                    "path": resolved.relative_to(self.repository_root).as_posix(),
                    "bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
        return {
            "files": files,
            "truncated": len(candidates) > max_files,
            "total_bytes": sum(int(item["bytes"]) for item in files),
        }

    def _queue_state(self, task_id: str | None) -> Literal["active", "complete", "unknown"]:
        if task_id is None:
            return "unknown"
        complete = self.repository_root / ".codex" / "queue" / "COMPLETE.md"
        active = self.repository_root / ".codex" / "queue" / "QUEUE.md"
        if complete.is_file() and re.search(rf"\b{re.escape(task_id)}\b", complete.read_text(encoding="utf-8")):
            return "complete"
        if active.is_file() and re.search(rf"\[TASK\s+{re.escape(task_id)}\]", active.read_text(encoding="utf-8")):
            return "active"
        return "unknown"

    def _successful_run(self, idempotency_key: str) -> dict[str, object] | None:
        for event in reversed(self._events()):
            if (
                event.get("event") == "script_run"
                and event.get("idempotency_key") == idempotency_key
                and event.get("status") == "succeeded"
            ):
                return event
        return None

    def _result(
        self,
        request: ScriptRunRequest,
        *,
        version: str,
        status: Literal["succeeded", "duplicate", "escalated", "rejected"],
        reason: str,
        data: dict[str, object],
        started: float,
        fallback: TaskRoute | None = None,
    ) -> ScriptRunResult:
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        result = ScriptRunResult(
            task_id=request.task_id,
            script_id=request.script_id,
            version=version,
            route=TaskRoute.SCRIPT,
            status=status,
            reason=reason,
            data=data,
            duration_ms=duration_ms,
            avoided_model_call=status in {"succeeded", "duplicate"},
            idempotency_key=request.idempotency_key,
            fallback=fallback,
        )
        self._append_event({"event": "script_run", **result.model_dump(mode="json")})
        return result

    def _events(self) -> list[dict[str, object]]:
        if not self.events_path.is_file():
            return []
        events: list[dict[str, object]] = []
        for line in self.events_path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    events.append(value)
            except json.JSONDecodeError:
                continue
        return events

    def _append_event(self, event: dict[str, object]) -> None:
        payload = {"timestamp": datetime.now(UTC).isoformat(), **event}
        with self._lock:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, separators=(",", ":")) + "\n")
