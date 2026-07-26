from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


PolicyProfileName = Literal["safe", "research", "open"]
AuditEventType = Literal[
    "task.queued",
    "target.start_requested",
    "safety.emergency_stop_engaged",
    "safety.emergency_stop_reset",
]


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class HealthResponse(BaseModel):
    service: str
    version: str
    status: Literal["ok"]
    environment: str
    executor_enabled: bool
    authentication_required: bool
    event_stream_enabled: bool = True


class TaskCreate(BaseModel):
    goal: str = Field(min_length=1, max_length=2_000)
    target_id: str = Field(min_length=1, max_length=120)
    policy_profile: PolicyProfileName = "safe"


class TaskRecord(TaskCreate):
    id: UUID
    status: TaskStatus
    created_at: datetime


class AuditEvent(BaseModel):
    sequence: int
    id: UUID
    event_type: AuditEventType
    task_id: UUID | None
    target_id: str | None
    message: str
    details: dict[str, object]
    created_at: datetime


class EmergencyStopEngageRequest(BaseModel):
    reason: str = Field(
        default="Operator requested emergency stop.",
        min_length=1,
        max_length=500,
    )


class EmergencyStopResetRequest(BaseModel):
    confirmation: Literal["RESET"]


class EmergencyStopState(BaseModel):
    engaged: bool
    reason: str | None
    generation: int = Field(ge=0)
    changed_at: datetime


class PolicyProfile(BaseModel):
    name: PolicyProfileName
    description: str
    confirmations_required: bool
    immutable_audit_log: bool = True
    isolated_target_required: bool = True
    emergency_stop_required: bool = True


class PluginSummary(BaseModel):
    id: str
    name: str
    version: str
    description: str
    enabled: bool = False
    protocol_version: Literal["1"]
    capabilities: tuple[str, ...]
    process_boundary: Literal["manifest-only", "out-of-process"]
    target_id: str | None = None


class ObservationPolicySummary(BaseModel):
    max_frame_width: int
    max_frame_bytes: int
    redaction_region_count: int
    evidence_retention: Literal["none"]
    max_retained_frames: Literal[0]
    retention_max_age_seconds: Literal[0]


class TargetSummary(BaseModel):
    id: str
    name: str
    transport: Literal["out-of-process-plugin"]
    mode: Literal["read-only"]
    connected: bool
    window_title: str
    frame_endpoint: str | None
    input_enabled: Literal[False] = False
    observer_plugin_id: str
    observer_process_boundary: Literal["out-of-process"]
    observation_status: Literal["ready", "unavailable"]
    observation_policy: ObservationPolicySummary
    start_enabled: bool = False
    start_endpoint: str | None = None


class TargetStartResponse(BaseModel):
    target_id: Literal["windows-sandbox"]
    status: Literal["starting", "already_running"]
    message: str


class EdgeAgentSummary(BaseModel):
    id: Literal["kali-pi"]
    name: str
    role: Literal["edge-agent"]
    transport: Literal["ssh-tunnel"]
    mode: Literal["read-only-advisory"]
    connected: bool
    version: str | None
    hostname: str | None
    target_count: int = Field(ge=0)
    recommendation_count: int = Field(ge=0)
