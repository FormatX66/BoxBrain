from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


PolicyProfileName = Literal["safe", "research", "open"]
AuditEventType = Literal[
    "task.queued",
    "target.start_requested",
    "remote_target.registered",
    "remote_target.removed",
    "remote_target.probed",
    "remote_target.session_opened",
    "diagnostic.proposed",
    "fleet.machine_registered",
    "fleet.targets_imported",
    "provisioning.started",
    "provisioning.step_completed",
    "diagnostic.execution_completed",
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


RemoteTransport = Literal["usb-c", "ssh", "winrm", "rdp", "telnet"]
RemoteTargetStatus = Literal["unknown", "online", "offline"]


class RemoteTargetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    transport: RemoteTransport
    host: str = Field(min_length=1, max_length=253)
    port: int | None = Field(default=None, ge=1, le=65_535)
    username: str | None = Field(default=None, max_length=120)
    authorization: Literal["AUTHORIZED"]
    insecure_transport_acknowledged: bool = False

    @field_validator("name", "host", "username")
    @classmethod
    def normalize_remote_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


class RemoteTargetRecord(BaseModel):
    id: UUID
    name: str
    transport: RemoteTransport
    host: str
    port: int = Field(ge=1, le=65_535)
    username: str | None
    authorized: bool = True
    built_in: bool = False
    status: RemoteTargetStatus = "unknown"
    credential_mode: Literal[
        "dedicated-key",
        "ssh-agent",
        "current-user",
        "interactive",
        "none",
    ]
    capabilities: tuple[str, ...]
    last_checked_at: datetime | None
    created_at: datetime


class RemoteTargetProbeResult(BaseModel):
    target_id: UUID
    status: Literal["online", "offline"]
    resolved_address: str | None
    latency_ms: int | None = Field(default=None, ge=0)
    message: str
    checked_at: datetime


class RemoteSessionRequest(BaseModel):
    confirmation: Literal["OPEN"]
    insecure_confirmation: str | None = Field(default=None, max_length=80)


class RemoteSessionResult(BaseModel):
    target_id: UUID
    status: Literal["opened"]
    application: str
    message: str


DiagnosticAction = Literal[
    "system_health",
    "disk_usage",
    "memory_usage",
    "uptime",
]
DiagnosticProposalStatus = Literal[
    "pending",
    "running",
    "succeeded",
    "failed",
    "expired",
]


class DiagnosticPlan(BaseModel):
    action: DiagnosticAction
    summary: str = Field(min_length=1, max_length=500)
    expected_evidence: str = Field(min_length=1, max_length=500)
    risk_note: str = Field(min_length=1, max_length=500)


class DiagnosticProposalRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=500)
    authorization: Literal["AUTHORIZED"]

    @field_validator("goal")
    @classmethod
    def normalize_diagnostic_goal(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("goal must contain non-whitespace text")
        return normalized


class DiagnosticProviderUsage(BaseModel):
    requests: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class DiagnosticProposal(BaseModel):
    id: UUID
    target_id: UUID
    target_name: str
    goal: str
    plan: DiagnosticPlan
    status: DiagnosticProposalStatus
    model: str
    usage: DiagnosticProviderUsage
    requires_confirmation: Literal[True] = True
    created_at: datetime
    expires_at: datetime


class DiagnosticExecuteRequest(BaseModel):
    confirmation: Literal["RUN"]


class DiagnosticExecutionResult(BaseModel):
    proposal_id: UUID
    target_id: UUID
    action: DiagnosticAction
    status: Literal["succeeded", "failed"]
    exit_code: int
    output: str
    truncated: bool
    duration_ms: int = Field(ge=0)
    executed_at: datetime


class DiagnosticRuntimeStatus(BaseModel):
    enabled: bool
    model_ready: bool
    executor_ready: bool
    model: str
    target_scope: Literal["built-in-kali-pi"] = "built-in-kali-pi"
    supported_actions: tuple[DiagnosticAction, ...]
    requires_confirmation: Literal[True] = True
    arbitrary_commands_enabled: Literal[False] = False


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
    network_interface: str | None = None
    wifi_credential_audit: Literal[
        "blocked", "exposed", "not-run", "unavailable"
    ] = "unavailable"
ProcessingAgentId = Literal[
    "orchestrator",
    "quartermaster",
    "sentinel",
    "librarian",
    "archivist",
    "scout",
    "task-manager",
    "architect",
    "engineer",
    "integrator",
]
ProcessingSource = Literal["voice", "chat", "api", "file"]
AgentStepStatus = Literal[
    "completed",
    "deferred",
    "approval_required",
]
ProcessingRunStatus = Literal[
    "completed",
    "partially_deferred",
    "needs_approval",
]
ProcessingArtifactKind = Literal[
    "normalized_input",
    "usage_plan",
    "security_note",
    "project_classification",
    "memory_note",
    "research_brief",
    "task",
    "architecture_brief",
    "implementation_brief",
    "integration_request",
]


class ProcessingAgentSummary(BaseModel):
    id: ProcessingAgentId
    name: str
    character: str
    responsibility: str
    capabilities: tuple[str, ...]
    execution_mode: Literal["local-rule", "planner-adapter"]
    enabled: bool = True


class ProcessingRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    source: ProcessingSource = "api"
    project_hint: str | None = Field(default=None, max_length=120)
    token_budget: int = Field(default=2_000, ge=128, le=100_000)
    external_access_allowed: bool = False

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must contain non-whitespace text")
        return value

    @field_validator("project_hint")
    @classmethod
    def normalize_project_hint(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


class ProcessingArtifact(BaseModel):
    kind: ProcessingArtifactKind
    title: str
    data: dict[str, object]


class ProcessingStep(BaseModel):
    agent_id: ProcessingAgentId
    status: AgentStepStatus
    summary: str
    estimated_tokens: int = Field(ge=0)
    artifacts: list[ProcessingArtifact] = Field(default_factory=list)


class UsageBudget(BaseModel):
    limit_tokens: int = Field(ge=0)
    estimated_input_tokens: int = Field(ge=0)
    estimated_reserved_tokens: int = Field(ge=0)
    estimated_remaining_tokens: int = Field(ge=0)
    provider_tokens_used: Literal[0] = 0
    execution_mode: Literal["local-rules"] = "local-rules"
    deferred_agents: list[ProcessingAgentId] = Field(default_factory=list)


class ProcessingRun(BaseModel):
    id: UUID
    source: ProcessingSource
    normalized_input: str
    project: str
    intent: str
    status: ProcessingRunStatus
    steps: list[ProcessingStep]
    artifacts: list[ProcessingArtifact]
    usage: UsageBudget
    created_at: datetime


class AgentUsageTotal(BaseModel):
    agent_id: ProcessingAgentId
    run_count: int = Field(ge=0)
    estimated_tokens: int = Field(ge=0)


class UsageSummary(BaseModel):
    total_runs: int = Field(ge=0)
    estimated_tokens: int = Field(ge=0)
    provider_tokens_used: int = Field(default=0, ge=0)
    by_agent: list[AgentUsageTotal]

MemoryKind = Literal["summary", "decision"]
AgentTaskStatus = Literal["open", "done", "dismissed"]


class ProjectSummary(BaseModel):
    key: str
    name: str
    memory_count: int = Field(ge=0)
    open_task_count: int = Field(ge=0)
    created_at: datetime
    last_activity_at: datetime


class MemoryRecord(BaseModel):
    id: UUID
    project_key: str
    project: str
    kind: MemoryKind
    content: str
    source_run_id: UUID
    created_at: datetime


class AgentTaskRecord(BaseModel):
    id: UUID
    project_key: str
    project: str
    title: str
    status: AgentTaskStatus
    source_run_id: UUID
    created_at: datetime
    updated_at: datetime


class AgentTaskStatusUpdate(BaseModel):
    status: AgentTaskStatus


class AgentDashboard(BaseModel):
    project_count: int = Field(ge=0)
    memory_count: int = Field(ge=0)
    open_task_count: int = Field(ge=0)
    completed_task_count: int = Field(ge=0)
    processing_run_count: int = Field(ge=0)
    estimated_tokens: int = Field(ge=0)
    provider_tokens_used: int = Field(default=0, ge=0)
    projects: list[ProjectSummary]
    recent_tasks: list[AgentTaskRecord]


class ModelAgentPlan(BaseModel):
    project: str = Field(min_length=1, max_length=120)
    intent: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=2_000)
    decisions: list[str] = Field(max_length=12)
    tasks: list[str] = Field(max_length=12)
    specialist_handoffs: list[ProcessingAgentId] = Field(
        max_length=10,
    )
    research_queries: list[str] = Field(max_length=8)
    architecture_notes: list[str] = Field(max_length=8)
    implementation_steps: list[str] = Field(max_length=12)
    integration_requests: list[str] = Field(max_length=8)
    risk_flags: list[str] = Field(max_length=8)
    requires_approval: bool


class ModelProviderUsage(BaseModel):
    requests: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class ModelProcessingRun(BaseModel):
    id: UUID
    local_run: ProcessingRun
    plan: ModelAgentPlan
    model: str
    usage: ModelProviderUsage
    execution_mode: Literal["openai-agents-sdk"] = "openai-agents-sdk"
    created_at: datetime


class ModelRuntimeStatus(BaseModel):
    enabled: bool
    configured: bool
    sdk_available: bool
    ready: bool
    model: str
    execution_mode: Literal["openai-agents-sdk"] = "openai-agents-sdk"
    external_side_effects_enabled: Literal[False] = False

ChatOrganizerSource = Literal["chatgpt_app_index", "chatgpt_data_export"]
ChatClassificationConfidence = Literal["high", "medium", "low"]


class ChatSourceProject(BaseModel):
    external_id: str = Field(min_length=1, max_length=500)
    label: str = Field(min_length=1, max_length=160)

    @field_validator("external_id", "label")
    @classmethod
    def normalize_project_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("project fields must contain non-whitespace text")
        return normalized


class ChatSourceRecord(BaseModel):
    external_id: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=500)
    updated_at: datetime
    project_external_id: str | None = Field(default=None, max_length=500)
    pinned_index: int | None = Field(default=None, ge=1)

    @field_validator("external_id", "title", "project_external_id")
    @classmethod
    def normalize_chat_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


class ChatOrganizerImportRequest(BaseModel):
    source: ChatOrganizerSource = "chatgpt_app_index"
    captured_at: datetime
    projects: list[ChatSourceProject] = Field(default_factory=list, max_length=500)
    chats: list[ChatSourceRecord] = Field(default_factory=list, max_length=20_000)


class OrganizedChatRecord(BaseModel):
    external_id: str
    title: str
    current_project_id: str | None
    current_project: str | None
    suggested_project: str
    classification_reason: str
    confidence: ChatClassificationConfidence
    pinned_index: int | None
    updated_at: datetime
    last_seen_at: datetime


class ChatOrganizerImportResult(BaseModel):
    id: UUID
    source: ChatOrganizerSource
    captured_at: datetime
    imported_at: datetime
    source_project_count: int = Field(ge=0)
    chat_count: int = Field(ge=0)
    created_count: int = Field(ge=0)
    updated_count: int = Field(ge=0)
    unchanged_count: int = Field(ge=0)
    unassigned_count: int = Field(ge=0)
    suggested_move_count: int = Field(ge=0)


class ChatProjectBucket(BaseModel):
    name: str
    chat_count: int = Field(ge=0)
    is_existing_chatgpt_project: bool


class ChatOrganizerDashboard(BaseModel):
    total_chat_count: int = Field(ge=0)
    source_project_count: int = Field(ge=0)
    unassigned_count: int = Field(ge=0)
    suggested_move_count: int = Field(ge=0)
    pinned_count: int = Field(ge=0)
    last_sync_at: datetime | None
    buckets: list[ChatProjectBucket]
    recent_chats: list[OrganizedChatRecord]
