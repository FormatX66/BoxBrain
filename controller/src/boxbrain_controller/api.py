from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from . import __version__
from .models import (
    HealthResponse,
    PluginSummary,
    PolicyProfile,
    TargetSummary,
    TaskCreate,
    TaskRecord,
)
from .plugin_registry import PluginRegistry
from .sandbox_observer import SandboxCaptureError, WindowsSandboxObserver
from .settings import settings
from .task_store import TaskStore

router = APIRouter(prefix="/api/v1")
task_store = TaskStore()
plugin_registry = PluginRegistry(settings.plugin_dir)
sandbox_observer = WindowsSandboxObserver()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        service="boxbrain-controller",
        version=__version__,
        status="ok",
        environment=settings.environment,
        executor_enabled=False,
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
    return [TargetSummary.model_validate(sandbox_observer.describe())]


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
