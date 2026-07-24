import asyncio
import json
from threading import Lock
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse

from . import __version__
from .models import (
    AuditEvent,
    EmergencyStopEngageRequest,
    EmergencyStopResetRequest,
    EmergencyStopState,
    HealthResponse,
    PluginSummary,
    PolicyProfile,
    TargetStartResponse,
    TargetSummary,
    TaskCreate,
    TaskRecord,
)
from .plugin_registry import PluginRegistry
from .sandbox_observer import (
    SandboxCaptureError,
    SandboxStartError,
    WindowsSandboxObserver,
)
from .settings import settings
from .task_store import TaskStore

router = APIRouter(prefix="/api/v1")
task_store = TaskStore(settings.data_dir / "boxbrain.sqlite3")
plugin_registry = PluginRegistry(settings.plugin_dir)
sandbox_observer = WindowsSandboxObserver(
    profile_path=settings.sandbox_profile,
    start_enabled=settings.sandbox_launch_enabled,
)
control_lock = Lock()


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    return HealthResponse(
        service="boxbrain-controller",
        version=__version__,
        status="ok",
        environment=settings.environment,
        executor_enabled=False,
        authentication_required=request.app.state.authentication_required,
    )


@router.get("/tasks", response_model=list[TaskRecord])
def list_tasks() -> list[TaskRecord]:
    return task_store.list()


@router.post(
    "/tasks",
    response_model=TaskRecord,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_task(request: TaskCreate) -> TaskRecord:
    if request.target_id != sandbox_observer.target_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target is not allowlisted.",
        )
    return task_store.create(request)


@router.get("/tasks/{task_id}", response_model=TaskRecord)
def get_task(task_id: UUID) -> TaskRecord:
    task = task_store.get(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    return task


@router.get("/events", response_model=list[AuditEvent])
def list_events(
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AuditEvent]:
    return task_store.list_events(limit=limit)


@router.get("/events/stream")
async def stream_events(
    request: Request,
    after_sequence: int = Query(default=0, ge=0),
) -> StreamingResponse:
    header_sequence = request.headers.get("Last-Event-ID")
    if header_sequence is not None:
        try:
            after_sequence = max(after_sequence, int(header_sequence))
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Last-Event-ID must be an audit sequence number.",
            ) from error

    async def event_source():
        cursor = after_sequence
        while not await request.is_disconnected():
            events = task_store.list_events_after(
                after_sequence=cursor,
                limit=100,
            )
            if events:
                for event in events:
                    cursor = event.sequence
                    payload = json.dumps(
                        event.model_dump(mode="json"),
                        separators=(",", ":"),
                    )
                    yield (
                        f"id: {event.sequence}\n"
                        f"event: {event.event_type}\n"
                        f"data: {payload}\n\n"
                    )
            else:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/safety/emergency-stop",
    response_model=EmergencyStopState,
)
def get_emergency_stop() -> EmergencyStopState:
    return task_store.get_emergency_stop()


@router.post(
    "/safety/emergency-stop/engage",
    response_model=EmergencyStopState,
)
def engage_emergency_stop(
    request: EmergencyStopEngageRequest,
) -> EmergencyStopState:
    with control_lock:
        return task_store.engage_emergency_stop(reason=request.reason)


@router.post(
    "/safety/emergency-stop/reset",
    response_model=EmergencyStopState,
)
def reset_emergency_stop(
    request: EmergencyStopResetRequest,
) -> EmergencyStopState:
    with control_lock:
        return task_store.reset_emergency_stop()


@router.get("/policies", response_model=list[PolicyProfile])
def list_policies() -> list[PolicyProfile]:
    return [
        PolicyProfile(
            name="safe",
            description="Confirm consequential actions and restrict capabilities.",
            confirmations_required=True,
        ),
        PolicyProfile(
            name="research",
            description=(
                "Reduce confirmations inside an isolated, resettable target."
            ),
            confirmations_required=False,
        ),
        PolicyProfile(
            name="open",
            description=(
                "Experimental profile for a disposable lab target; containment, "
                "audit logging, and emergency stop remain mandatory."
            ),
            confirmations_required=False,
        ),
    ]


@router.get("/plugins", response_model=list[PluginSummary])
def list_plugins() -> list[PluginSummary]:
    return plugin_registry.discover()


@router.get("/targets", response_model=list[TargetSummary])
def list_targets() -> list[TargetSummary]:
    target = TargetSummary.model_validate(sandbox_observer.describe())
    if task_store.get_emergency_stop().engaged:
        target.start_enabled = False
        target.start_endpoint = None
    return [target]


@router.post(
    "/targets/windows-sandbox/start",
    response_model=TargetStartResponse,
)
def start_windows_sandbox() -> TargetStartResponse:
    if not settings.sandbox_launch_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sandbox launch is disabled outside development.",
        )
    with control_lock:
        emergency_stop = task_store.get_emergency_stop()
        if emergency_stop.engaged:
            task_store.append_event(
                event_type="target.start_requested",
                target_id=sandbox_observer.target_id,
                message="Windows Sandbox launch blocked by emergency stop.",
                details={
                    "result": "blocked",
                    "reason": "emergency_stop",
                    "generation": emergency_stop.generation,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Emergency stop is engaged. Reset it before launching Sandbox.",
            )
        try:
            launch_status = sandbox_observer.start()
        except SandboxStartError as error:
            task_store.append_event(
                event_type="target.start_requested",
                target_id=sandbox_observer.target_id,
                message="Windows Sandbox launch failed.",
                details={"result": "failed", "reason": str(error)},
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error

        message = (
            "Windows Sandbox is already running."
            if launch_status == "already_running"
            else "Windows Sandbox launch requested."
        )
        task_store.append_event(
            event_type="target.start_requested",
            target_id=sandbox_observer.target_id,
            message=message,
            details={"result": launch_status},
        )
    return TargetStartResponse(
        target_id="windows-sandbox",
        status=launch_status,
        message=message,
    )


@router.get(
    "/targets/windows-sandbox/frame",
    response_class=Response,
    responses={
        200: {"content": {"image/png": {}}},
        404: {"description": "Windows Sandbox is not running"},
        503: {"description": "Frame capture is unavailable"},
    },
)
def get_windows_sandbox_frame() -> Response:
    if sandbox_observer.find_window() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Windows Sandbox is not running.",
        )
    try:
        frame = sandbox_observer.capture_png()
    except SandboxCaptureError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    return Response(
        content=frame,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store, max-age=0",
            "X-BoxBrain-Capture-Mode": "read-only",
            "X-Content-Type-Options": "nosniff",
        },
    )
