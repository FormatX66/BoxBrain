import asyncio
import hashlib
import json
from threading import Lock
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse

from . import __version__
from .edge_agent import KaliPiEdgeAgentClient
from .models import (
    AgentDashboard,
    AgentTaskRecord,
    AgentTaskStatus,
    AgentTaskStatusUpdate,
    AuditEvent,
    ChatOrganizerDashboard,
    ChatOrganizerImportRequest,
    ChatOrganizerImportResult,
    EdgeAgentSummary,
    EmergencyStopEngageRequest,
    EmergencyStopResetRequest,
    EmergencyStopState,
    HealthResponse,
    MemoryRecord,
    ModelProcessingRun,
    ModelRuntimeStatus,
    OrganizedChatRecord,
    PluginSummary,
    PolicyProfile,
    ProcessingAgentSummary,
    ProcessingRequest,
    ProcessingRun,
    ProjectSummary,
    TargetStartResponse,
    TargetSummary,
    TaskCreate,
    TaskRecord,
    UsageSummary,
)
from .chat_organizer import ChatOrganizerService
from .model_agents import (
    ModelAgentExecutionError,
    ModelAgentRuntimeUnavailable,
    ModelAgentService,
)
from .observation_policy import ObservationPolicy
from .plugin_process import (
    ObserverPluginClient,
    OutOfProcessWindowsSandboxObserver,
)
from .plugin_registry import PluginRegistry
from .processing_agents import ProcessingService
from .processing_store import ProcessingStore
from .sandbox_observer import (
    SandboxCaptureError,
    SandboxNotRunningError,
    SandboxObservationBusyError,
    SandboxStartError,
    WindowsSandboxObserver,
)
from .settings import settings
from .task_store import TaskStore

router = APIRouter(prefix="/api/v1")
task_store = TaskStore(settings.data_dir / "boxbrain.sqlite3")
processing_store = ProcessingStore(settings.data_dir / "boxbrain.sqlite3")
processing_service = ProcessingService(processing_store)
chat_organizer_service = ChatOrganizerService(
    settings.data_dir / "boxbrain.sqlite3"
)
model_agent_service = ModelAgentService(
    processing_service,
    enabled=settings.agent_runtime_enabled,
    model=settings.agent_model,
    max_output_tokens=settings.agent_max_output_tokens,
)
plugin_registry = PluginRegistry(settings.plugin_dir)
observation_policy = ObservationPolicy.load(settings.observation_policy_path)
sandbox_launcher = WindowsSandboxObserver(
    profile_path=settings.sandbox_profile,
    start_enabled=settings.sandbox_launch_enabled,
)
sandbox_observer = OutOfProcessWindowsSandboxObserver(
    ObserverPluginClient(
        registry=plugin_registry,
        plugin_id=settings.observer_plugin_id,
        policy=observation_policy,
    ),
    launcher=sandbox_launcher,
)
edge_agent_client = KaliPiEdgeAgentClient(
    settings.kali_pi_agent_url,
    timeout_seconds=settings.kali_pi_agent_timeout_seconds,
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


@router.get("/agents", response_model=list[ProcessingAgentSummary])
def list_processing_agents() -> list[ProcessingAgentSummary]:
    return processing_service.list_agents()


@router.get("/agents/runtime", response_model=ModelRuntimeStatus)
def get_model_agent_runtime() -> ModelRuntimeStatus:
    return model_agent_service.runtime_status()


@router.post("/processing/runs", response_model=ProcessingRun)
def create_processing_run(request: ProcessingRequest) -> ProcessingRun:
    return processing_service.process(request)


@router.post("/processing/model-runs", response_model=ModelProcessingRun)
async def create_model_processing_run(
    request: ProcessingRequest,
) -> ModelProcessingRun:
    try:
        return await model_agent_service.process(request)
    except ModelAgentRuntimeUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except ModelAgentExecutionError as error:
        provider_status = {
            "access": status.HTTP_403_FORBIDDEN,
            "rate_limit": status.HTTP_429_TOO_MANY_REQUESTS,
            "quota": status.HTTP_503_SERVICE_UNAVAILABLE,
            "authentication": status.HTTP_503_SERVICE_UNAVAILABLE,
        }.get(error.category, status.HTTP_502_BAD_GATEWAY)
        raise HTTPException(
            status_code=provider_status,
            detail=str(error),
        ) from error


@router.get(
    "/processing/model-runs",
    response_model=list[ModelProcessingRun],
)
def list_model_processing_runs(
    limit: int = Query(default=100, ge=1, le=500),
) -> list[ModelProcessingRun]:
    return model_agent_service.list_runs(limit=limit)


@router.get(
    "/processing/model-runs/{run_id}",
    response_model=ModelProcessingRun,
)
def get_model_processing_run(run_id: UUID) -> ModelProcessingRun:
    run = model_agent_service.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model processing run not found",
        )
    return run


@router.get("/processing/runs", response_model=list[ProcessingRun])
def list_processing_runs(
    limit: int = Query(default=100, ge=1, le=500),
) -> list[ProcessingRun]:
    return processing_service.list_runs(limit=limit)


@router.get("/processing/runs/{run_id}", response_model=ProcessingRun)
def get_processing_run(run_id: UUID) -> ProcessingRun:
    run = processing_service.get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Processing run not found",
        )
    return run


@router.get("/processing/usage", response_model=UsageSummary)
def get_processing_usage() -> UsageSummary:
    return processing_service.usage_summary()


@router.get("/agent-dashboard", response_model=AgentDashboard)
def get_agent_dashboard() -> AgentDashboard:
    return processing_service.dashboard()


@router.post(
    "/chat-organizer/import",
    response_model=ChatOrganizerImportResult,
)
def import_chat_organizer_snapshot(
    request: ChatOrganizerImportRequest,
) -> ChatOrganizerImportResult:
    return chat_organizer_service.import_snapshot(request)


@router.get(
    "/chat-organizer",
    response_model=ChatOrganizerDashboard,
)
def get_chat_organizer_dashboard() -> ChatOrganizerDashboard:
    return chat_organizer_service.dashboard()


@router.get(
    "/chat-organizer/chats",
    response_model=list[OrganizedChatRecord],
)
def list_organized_chats(
    project: str | None = Query(default=None, min_length=1, max_length=160),
    unassigned_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[OrganizedChatRecord]:
    return chat_organizer_service.list_chats(
        project=project,
        unassigned_only=unassigned_only,
        limit=limit,
    )


@router.get(
    "/chat-organizer/imports",
    response_model=list[ChatOrganizerImportResult],
)
def list_chat_organizer_imports(
    limit: int = Query(default=50, ge=1, le=500),
) -> list[ChatOrganizerImportResult]:
    return chat_organizer_service.list_imports(limit=limit)


@router.get("/projects", response_model=list[ProjectSummary])
def list_agent_projects() -> list[ProjectSummary]:
    return processing_service.list_projects()


@router.get("/memory", response_model=list[MemoryRecord])
def list_agent_memory(
    project: str | None = Query(default=None, min_length=1, max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[MemoryRecord]:
    return processing_service.list_memory(project=project, limit=limit)


@router.get("/memory/search", response_model=list[MemoryRecord])
def search_agent_memory(
    q: str = Query(min_length=2, max_length=500),
    project: str | None = Query(default=None, min_length=1, max_length=120),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[MemoryRecord]:
    return processing_service.search_memory(
        query=q,
        project=project,
        limit=limit,
    )


@router.get("/agent-tasks", response_model=list[AgentTaskRecord])
def list_agent_tasks(
    project: str | None = Query(default=None, min_length=1, max_length=120),
    task_status: AgentTaskStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AgentTaskRecord]:
    return processing_service.list_agent_tasks(
        project=project,
        task_status=task_status,
        limit=limit,
    )


@router.post(
    "/agent-tasks/{task_id}/status",
    response_model=AgentTaskRecord,
)
def update_agent_task_status(
    task_id: UUID,
    request: AgentTaskStatusUpdate,
) -> AgentTaskRecord:
    task = processing_service.update_agent_task(
        task_id,
        task_status=request.status,
    )
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent task not found",
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


@router.get("/edge-agents", response_model=list[EdgeAgentSummary])
def list_edge_agents() -> list[EdgeAgentSummary]:
    return [edge_agent_client.describe()]


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
        429: {"description": "Another frame capture is in progress"},
        503: {"description": "Frame capture is unavailable"},
    },
)
def get_windows_sandbox_frame() -> Response:
    try:
        frame = sandbox_observer.capture_png()
    except SandboxObservationBusyError as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(error),
            headers={"Retry-After": "1"},
        ) from error
    except SandboxNotRunningError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
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
            "X-BoxBrain-Frame-SHA256": hashlib.sha256(frame).hexdigest(),
            "X-BoxBrain-Redaction-Regions": str(
                len(observation_policy.redaction_regions)
            ),
            "X-BoxBrain-Evidence-Retention": (
                observation_policy.evidence_retention.mode
            ),
            "X-BoxBrain-Frame-Max-Width": str(
                observation_policy.max_frame_width
            ),
            "X-BoxBrain-Frame-Max-Bytes": str(
                observation_policy.max_frame_bytes
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )
