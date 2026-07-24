from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


PolicyProfileName = Literal["safe", "research", "open"]


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


class TaskCreate(BaseModel):
    goal: str = Field(min_length=1, max_length=2_000)
    target_id: str = Field(min_length=1, max_length=120)
    policy_profile: PolicyProfileName = "safe"


class TaskRecord(TaskCreate):
    id: UUID
    status: TaskStatus
    created_at: datetime


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


class TargetSummary(BaseModel):
    id: str
    name: str
    transport: Literal["local-window-capture"]
    mode: Literal["read-only"]
    connected: bool
    window_title: str
    frame_endpoint: str | None
    input_enabled: Literal[False] = False
