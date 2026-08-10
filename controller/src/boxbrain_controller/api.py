import asyncio
import hashlib
import json
from threading import Lock
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse

from . import __version__
from .architecture_manifest import (
    ArchitectureAgent,
    ArchitectureManifest,
    get_architecture_manifest,
)
from .diagnostic_executor import (
    DiagnosticError,
    DiagnosticExecutionUnavailable,
    DiagnosticExecutorService,
    DiagnosticNotFoundError,
    DiagnosticRuntimeUnavailable,
)
from .edge_agent import KaliPiEdgeAgentClient
from .fleet import (
    FleetDashboard,
    FleetError,
    FleetImportRequest,
    FleetMachine,
    FleetMachineCreate,
    FleetMachineNotFoundError,
    FleetService,
    ProvisioningNotFoundError,
    ProvisioningRun,
    ProvisioningStartRequest,
    ProvisioningStepCompleteRequest,
)
from .models import (
    AgentDashboard,
    AgentTaskRecord,
    AgentTaskStatus,
    AgentTaskStatusUpdate,
    AuditEvent,
    ChatOrganizerDashboard,
    ChatOrganizerImportRequest,
    ChatOrganizerImportResult,
    DiagnosticExecuteRequest,
    DiagnosticExecutionResult,
    DiagnosticProposal,
    DiagnosticProposalRequest,
    DiagnosticRuntimeStatus,
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
    RemoteSessionRequest,
    RemoteSessionResult,
    RemoteTargetCreate,
    RemoteTargetProbeResult,
    RemoteTargetRecord,
    TargetStartResponse,
    TargetSummary,
    TaskCreate,
    TaskRecord,
    UsageSummary,
)
from .chat_organizer import ChatOrganizerService
from .copilot_offload import (
    CopilotDispatchRequest,
    CopilotDispatchResult,
    CopilotOffloadError,
    CopilotOffloadService,
    CopilotPacketNotFoundError,
    CopilotPrepareRequest,
    CopilotProviderRuntime,
    CopilotRuntimeStatus,
    CopilotRuntimeUnavailable,
    CopilotWorkPacket,
)
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
from .script_first import (
    RouteDecision,
    RouteRequest,
    RoutingMetrics,
    ScriptFirstService,
    ScriptRunRequest,
    ScriptRunResult,
    ScriptSpec,
)
from .remote_targets import (
    RemoteSessionLaunchError,
    RemoteTargetError,
    RemoteTargetNotFoundError,
    RemoteTargetScopeError,
    RemoteTargetService,
)
from .settings import settings
from .task_store import TaskStore
from .workflow_optimizer import (
    WorkflowOptimizeRequest,
    WorkflowOptimizerService,
    WorkflowPlan,
)

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
remote_target_service = RemoteTargetService(
    settings.data_dir / "boxbrain.sqlite3",
    usb_identity_file=settings.remote_usb_identity_file,
)
fleet_service = FleetService(settings.data_dir / "boxbrain.sqlite3")
diagnostic_executor_service = DiagnosticExecutorService(
    settings.data_dir / "boxbrain.sqlite3",
    remote_target_service,
    enabled=settings.diagnostic_executor_enabled,
    model=settings.agent_model,
    max_output_tokens=settings.agent_max_output_tokens,
    usb_identity_file=settings.remote_usb_identity_file,
    timeout_seconds=settings.diagnostic_timeout_seconds,
    max_output_bytes=settings.diagnostic_max_output_bytes,
)
control_lock = Lock()
script_first_service = ScriptFirstService(
    settings.repository_root,
    settings.data_dir,
)
copilot_offload_service = CopilotOffloadService(
    settings.repository_root,
    settings.data_dir,
    allowed_roots=settings.github_copilot_allowed_roots,
    enabled=settings.github_copilot_offload_enabled,
    timeout_seconds=settings.github_copilot_timeout_seconds,
    max_files=settings.github_copilot_max_files,
    max_file_bytes=settings.github_copilot_max_file_bytes,
    max_content_bytes=settings.github_copilot_max_content_bytes,
    max_output_bytes=settings.github_copilot_max_output_bytes,
)
workflow_optimizer_service = WorkflowOptimizerService(
    script_first_service,
    copilot_offload_service,
)


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

@router.get("/architecture", response_model=ArchitectureManifest)
def get_system_architecture() -> ArchitectureManifest:
    return get_architecture_manifest()


@router.get("/system-agents", response_model=list[ArchitectureAgent])
def list_system_agents() -> list[ArchitectureAgent]:
    return list(get_architecture_manifest().agents)


@router.get("/fleet", response_model=FleetDashboard)
def get_fleet_dashboard() -> FleetDashboard:
    return fleet_service.dashboard()


@router.get("/fleet/machines", response_model=list[FleetMachine])
def list_fleet_machines() -> list[FleetMachine]:
    return fleet_service.list()


@router.post(
    "/fleet/machines",
    response_model=FleetMachine,
    status_code=status.HTTP_201_CREATED,
)
def register_fleet_machine(request: FleetMachineCreate) -> FleetMachine:
    if request.remote_target_id is not None:
        try:
            remote_target_service.get(request.remote_target_id)
        except RemoteTargetNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Select a registered remote target.",
            ) from error
    try:
        machine = fleet_service.create(request)
    except FleetError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    task_store.append_event(
        event_type="fleet.machine_registered",
        target_id=f"machine:{machine.id}",
        message=f"Registered fleet machine {machine.name}.",
        details={
            "result": "registered",
            "machine_identity": machine.machine_identity,
            "kind": machine.kind,
            "remote_target_linked": machine.remote_target_id is not None,
        },
    )
    return machine


@router.post(
    "/fleet/import-targets",
    response_model=list[FleetMachine],
)
def import_remote_targets_to_fleet(
    request: FleetImportRequest,
) -> list[FleetMachine]:
    del request
    try:
        machines = fleet_service.import_remote_targets(remote_target_service.list())
    except FleetError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    task_store.append_event(
        event_type="fleet.targets_imported",
        target_id=None,
        message="Synchronized authorized remote targets into Fleet Manager.",
        details={"result": "synchronized", "machine_count": len(machines)},
    )
    return machines


@router.get(
    "/fleet/machines/{machine_id}/provisioning",
    response_model=ProvisioningRun | None,
)
def get_machine_provisioning(machine_id: UUID) -> ProvisioningRun | None:
    try:
        return fleet_service.get_provisioning(machine_id)
    except FleetMachineNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error


@router.post(
    "/fleet/machines/{machine_id}/provisioning",
    response_model=ProvisioningRun,
    status_code=status.HTTP_201_CREATED,
)
def start_machine_provisioning(
    machine_id: UUID,
    request: ProvisioningStartRequest,
) -> ProvisioningRun:
    del request
    try:
        run = fleet_service.start_provisioning(machine_id)
        machine = fleet_service.get(machine_id)
    except FleetMachineNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    task_store.append_event(
        event_type="provisioning.started",
        target_id=f"machine:{machine.id}",
        message=f"Provisioning workflow ready for {machine.name}.",
        details={
            "result": run.status,
            "run_id": str(run.id),
            "current_step_id": run.current_step_id or "complete",
        },
    )
    return run


@router.post(
    "/provisioning/{run_id}/steps/{step_id}/complete",
    response_model=ProvisioningRun,
)
def complete_provisioning_step(
    run_id: UUID,
    step_id: str,
    request: ProvisioningStepCompleteRequest,
) -> ProvisioningRun:
    try:
        run = fleet_service.complete_step(run_id, step_id, request)
    except ProvisioningNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except FleetError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    task_store.append_event(
        event_type="provisioning.step_completed",
        target_id=f"machine:{run.machine_id}",
        message=f"Completed provisioning step {step_id}.",
        details={
            "result": run.status,
            "run_id": str(run.id),
            "step_id": step_id,
            "next_step_id": run.current_step_id or "complete",
        },
    )
    return run


@router.get("/agents/runtime", response_model=ModelRuntimeStatus)
def get_model_agent_runtime() -> ModelRuntimeStatus:
    return model_agent_service.runtime_status()


@router.get(
    "/agents/diagnostic-runtime",
    response_model=DiagnosticRuntimeStatus,
)
def get_diagnostic_runtime() -> DiagnosticRuntimeStatus:
    return diagnostic_executor_service.runtime_status()


@router.post("/processing/runs", response_model=ProcessingRun)
def create_processing_run(request: ProcessingRequest) -> ProcessingRun:
    return processing_service.process(request)


@router.get("/processing/script-registry", response_model=list[ScriptSpec])
def list_script_registry() -> list[ScriptSpec]:
    return script_first_service.list_scripts()


@router.post("/processing/route", response_model=RouteDecision)
def classify_processing_route(request: RouteRequest) -> RouteDecision:
    return script_first_service.classify(request)


@router.post("/processing/script-runs", response_model=ScriptRunResult)
def run_registered_script(request: ScriptRunRequest) -> ScriptRunResult:
    return script_first_service.execute(request)


@router.get("/processing/script-metrics", response_model=RoutingMetrics)
def get_script_routing_metrics() -> RoutingMetrics:
    return script_first_service.metrics()


@router.post("/processing/workflows/optimize", response_model=WorkflowPlan)
def optimize_processing_workflow(request: WorkflowOptimizeRequest) -> WorkflowPlan:
    return workflow_optimizer_service.optimize(request)


@router.get("/processing/copilot/runtime", response_model=CopilotRuntimeStatus)
def get_copilot_runtime() -> CopilotRuntimeStatus:
    return copilot_offload_service.runtime_status()


@router.get(
    "/processing/copilot/providers",
    response_model=tuple[CopilotProviderRuntime, ...],
)
def list_copilot_providers() -> tuple[CopilotProviderRuntime, ...]:
    return copilot_offload_service.runtime_status().providers


@router.post("/processing/copilot/packets", response_model=CopilotWorkPacket)
def prepare_copilot_packet(request: CopilotPrepareRequest) -> CopilotWorkPacket:
    try:
        return copilot_offload_service.prepare(request)
    except CopilotOffloadError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error


@router.post("/processing/copilot/dispatches", response_model=CopilotDispatchResult)
def dispatch_copilot_packet(request: CopilotDispatchRequest) -> CopilotDispatchResult:
    try:
        return copilot_offload_service.dispatch(request)
    except CopilotPacketNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except CopilotRuntimeUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except CopilotOffloadError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error


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


@router.get("/remote-targets", response_model=list[RemoteTargetRecord])
def list_remote_targets() -> list[RemoteTargetRecord]:
    return remote_target_service.list()


@router.post(
    "/remote-targets",
    response_model=RemoteTargetRecord,
    status_code=status.HTTP_201_CREATED,
)
def register_remote_target(request: RemoteTargetCreate) -> RemoteTargetRecord:
    try:
        record = remote_target_service.create(request)
    except RemoteTargetError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    task_store.append_event(
        event_type="remote_target.registered",
        target_id=f"remote:{record.id}",
        message=f"Authorized {record.transport} target registered.",
        details={
            "result": "registered",
            "transport": record.transport,
            "host": record.host,
            "port": record.port,
        },
    )
    return record


@router.delete(
    "/remote-targets/{target_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_remote_target(target_id: UUID) -> Response:
    try:
        record = remote_target_service.delete(target_id)
    except RemoteTargetNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except RemoteTargetError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    task_store.append_event(
        event_type="remote_target.removed",
        target_id=f"remote:{record.id}",
        message="Authorized remote target removed.",
        details={"result": "removed", "transport": record.transport},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/remote-targets/{target_id}/probe",
    response_model=RemoteTargetProbeResult,
)
def probe_remote_target(target_id: UUID) -> RemoteTargetProbeResult:
    try:
        result = remote_target_service.probe(target_id)
        record = remote_target_service.get(target_id)
    except RemoteTargetNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except RemoteTargetScopeError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    task_store.append_event(
        event_type="remote_target.probed",
        target_id=f"remote:{record.id}",
        message=f"{record.transport.upper()} target probe: {result.status}.",
        details={
            "result": result.status,
            "transport": record.transport,
            "port": record.port,
            "latency_ms": result.latency_ms,
        },
    )
    return result


@router.post(
    "/remote-targets/{target_id}/session",
    response_model=RemoteSessionResult,
)
def open_remote_target_session(
    target_id: UUID,
    request: RemoteSessionRequest,
) -> RemoteSessionResult:
    with control_lock:
        emergency_stop = task_store.get_emergency_stop()
        if emergency_stop.engaged:
            task_store.append_event(
                event_type="remote_target.session_opened",
                target_id=f"remote:{target_id}",
                message="Remote session blocked by emergency stop.",
                details={
                    "result": "blocked",
                    "reason": "emergency_stop",
                    "generation": emergency_stop.generation,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Emergency stop is engaged. Reset it before opening a session.",
            )
        try:
            result = remote_target_service.open_session(target_id, request)
            record = remote_target_service.get(target_id)
        except RemoteTargetNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        except (RemoteTargetError, RemoteTargetScopeError) as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(error),
            ) from error
        except RemoteSessionLaunchError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error
        task_store.append_event(
            event_type="remote_target.session_opened",
            target_id=f"remote:{record.id}",
            message=result.message,
            details={
                "result": result.status,
                "transport": record.transport,
                "application": result.application,
            },
        )
    return result


@router.get(
    "/remote-targets/{target_id}/diagnostic-proposals",
    response_model=list[DiagnosticProposal],
)
def list_diagnostic_proposals(
    target_id: UUID,
    limit: int = Query(default=25, ge=1, le=100),
) -> list[DiagnosticProposal]:
    try:
        remote_target_service.get(target_id)
    except RemoteTargetNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    return diagnostic_executor_service.list(target_id=target_id, limit=limit)


@router.post(
    "/remote-targets/{target_id}/diagnostic-proposals",
    response_model=DiagnosticProposal,
    status_code=status.HTTP_201_CREATED,
)
async def create_diagnostic_proposal(
    target_id: UUID,
    request: DiagnosticProposalRequest,
) -> DiagnosticProposal:
    try:
        proposal = await diagnostic_executor_service.propose(target_id, request)
    except RemoteTargetNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except DiagnosticRuntimeUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except DiagnosticError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    task_store.append_event(
        event_type="diagnostic.proposed",
        target_id=f"remote:{proposal.target_id}",
        message=f"AI proposed the {proposal.plan.action} diagnostic.",
        details={
            "result": "pending_approval",
            "proposal_id": str(proposal.id),
            "action": proposal.plan.action,
            "model": proposal.model,
            "provider_tokens": proposal.usage.total_tokens,
            "expires_at": proposal.expires_at.isoformat(),
        },
    )
    return proposal


@router.post(
    "/diagnostic-proposals/{proposal_id}/execute",
    response_model=DiagnosticExecutionResult,
)
def execute_diagnostic_proposal(
    proposal_id: UUID,
    request: DiagnosticExecuteRequest,
) -> DiagnosticExecutionResult:
    del request
    with control_lock:
        emergency_stop = task_store.get_emergency_stop()
        if emergency_stop.engaged:
            task_store.append_event(
                event_type="diagnostic.execution_completed",
                target_id=None,
                message="Diagnostic execution blocked by emergency stop.",
                details={
                    "result": "blocked",
                    "proposal_id": str(proposal_id),
                    "reason": "emergency_stop",
                    "generation": emergency_stop.generation,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=(
                    "Emergency stop is engaged. Reset it before running a "
                    "diagnostic."
                ),
            )
        try:
            result = diagnostic_executor_service.execute(proposal_id)
        except DiagnosticNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        except RemoteTargetNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        except RemoteTargetError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(error),
            ) from error
        except DiagnosticError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        except (
            DiagnosticRuntimeUnavailable,
            DiagnosticExecutionUnavailable,
        ) as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error
        task_store.append_event(
            event_type="diagnostic.execution_completed",
            target_id=f"remote:{result.target_id}",
            message=(
                f"Approved {result.action} diagnostic {result.status}."
            ),
            details={
                "result": result.status,
                "proposal_id": str(result.proposal_id),
                "action": result.action,
                "exit_code": result.exit_code,
                "duration_ms": result.duration_ms,
                "truncated": result.truncated,
            },
        )
    return result


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
