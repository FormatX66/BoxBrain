from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from .models import (
    AgentDashboard,
    AgentStepStatus,
    AgentTaskRecord,
    AgentTaskStatus,
    MemoryRecord,
    ProcessingAgentId,
    ProcessingAgentSummary,
    ProcessingArtifact,
    ProcessingArtifactKind,
    ProcessingRequest,
    ProcessingRun,
    ProcessingRunStatus,
    ProcessingStep,
    ProjectSummary,
    UsageBudget,
    UsageSummary,
)
from .processing_store import ProcessingStore


@dataclass(frozen=True, slots=True)
class _AgentDefinition:
    summary: ProcessingAgentSummary
    base_tokens: int
    input_ratio: float


_AGENTS = (
    _AgentDefinition(
        ProcessingAgentSummary(
            id="orchestrator",
            name="Orchestrator",
            character="The Conductor",
            responsibility="Normalize intake, identify intent, and route work.",
            capabilities=("intake", "routing", "fallback"),
            execution_mode="local-rule",
        ),
        16,
        0.08,
    ),
    _AgentDefinition(
        ProcessingAgentSummary(
            id="quartermaster",
            name="Usage Controller",
            character="The Quartermaster",
            responsibility="Estimate usage, enforce budgets, and defer optional work.",
            capabilities=("token-estimation", "budgeting", "deduplication"),
            execution_mode="local-rule",
        ),
        8,
        0.0,
    ),
    _AgentDefinition(
        ProcessingAgentSummary(
            id="sentinel",
            name="Security Agent",
            character="The Sentinel",
            responsibility="Flag effectful or sensitive work before execution.",
            capabilities=("risk-screening", "approval-gates", "policy-notes"),
            execution_mode="local-rule",
        ),
        10,
        0.03,
    ),
    _AgentDefinition(
        ProcessingAgentSummary(
            id="librarian",
            name="Project Librarian",
            character="The Librarian",
            responsibility="Classify material into the correct project.",
            capabilities=("classification", "project-indexing", "filing"),
            execution_mode="local-rule",
        ),
        12,
        0.04,
    ),
    _AgentDefinition(
        ProcessingAgentSummary(
            id="archivist",
            name="Knowledge Manager",
            character="The Archivist",
            responsibility="Turn conversations into durable project memory.",
            capabilities=("summaries", "decisions", "memory-notes"),
            execution_mode="planner-adapter",
        ),
        14,
        0.05,
    ),
    _AgentDefinition(
        ProcessingAgentSummary(
            id="scout",
            name="Search and Memory Agent",
            character="The Scout",
            responsibility="Prepare focused retrieval and research handoffs.",
            capabilities=("retrieval-plan", "research-brief", "source-routing"),
            execution_mode="planner-adapter",
        ),
        18,
        0.06,
    ),
    _AgentDefinition(
        ProcessingAgentSummary(
            id="task-manager",
            name="Task Manager",
            character="The Dispatcher",
            responsibility="Extract concrete next actions and dependencies.",
            capabilities=("task-extraction", "prioritization", "handoffs"),
            execution_mode="planner-adapter",
        ),
        14,
        0.05,
    ),
    _AgentDefinition(
        ProcessingAgentSummary(
            id="architect",
            name="Architecture Agent",
            character="The Architect",
            responsibility="Shape systems, flows, and implementation boundaries.",
            capabilities=("system-design", "data-flow", "contracts"),
            execution_mode="planner-adapter",
        ),
        18,
        0.06,
    ),
    _AgentDefinition(
        ProcessingAgentSummary(
            id="engineer",
            name="Engineering Agent",
            character="The Engineer",
            responsibility="Prepare code, test, and build implementation work.",
            capabilities=("implementation-plan", "test-plan", "code-handoff"),
            execution_mode="planner-adapter",
        ),
        20,
        0.08,
    ),
    _AgentDefinition(
        ProcessingAgentSummary(
            id="integrator",
            name="Integration Agent",
            character="The Bridge",
            responsibility="Route work to approved email, calendar, file, and code services.",
            capabilities=("connector-routing", "permission-gates", "sync-plan"),
            execution_mode="planner-adapter",
        ),
        18,
        0.06,
    ),
)
_AGENT_BY_ID = {agent.summary.id: agent for agent in _AGENTS}
_CORE_AGENT_IDS: tuple[ProcessingAgentId, ...] = (
    "orchestrator",
    "quartermaster",
    "sentinel",
    "librarian",
    "archivist",
    "task-manager",
)
_OPTIONAL_KEYWORDS: dict[ProcessingAgentId, tuple[str, ...]] = {
    "scout": (
        "find",
        "look up",
        "research",
        "search",
        "source",
        "verify",
        "web",
    ),
    "architect": (
        "agent",
        "architecture",
        "design",
        "flow",
        "organization",
        "system",
        "workflow",
    ),
    "engineer": (
        "build",
        "code",
        "debug",
        "fix",
        "github",
        "implement",
        "repo",
        "test",
        "website",
    ),
    "integrator": (
        "box",
        "calendar",
        "drive",
        "email",
        "gmail",
        "github",
        "inbox",
        "mail",
        "slack",
        "sync",
    ),
}
_PROJECT_PATTERNS = (
    ("BoxBrain", ("boxbrain", "box brain")),
    ("ArkmatX", ("arkmatx", "ubercorp")),
    ("Wet Beard", ("wet beard", "wetbeard")),
    ("BrainConnect", ("brainconnect", "brain connect")),
)
_RISK_PATTERNS = (
    r"\bdelete\b",
    r"\bdeploy\b",
    r"\bformat\s+(?:a\s+)?(?:disk|drive|card)\b",
    r"\bpay\b",
    r"\bpublish\b",
    r"\bpurchase\b",
    r"\breset\b",
    r"\bsend\b",
    r"\btransfer\b",
)
_TASK_VERBS = (
    "add",
    "build",
    "check",
    "clean",
    "connect",
    "create",
    "debug",
    "design",
    "fix",
    "implement",
    "organize",
    "pull",
    "review",
    "set up",
    "sync",
    "test",
    "update",
)


class ProcessingService:
    """Provider-neutral intake and planning pipeline for the BoxBrain crew."""

    def __init__(self, store: ProcessingStore) -> None:
        self.store = store

    @staticmethod
    def list_agents() -> list[ProcessingAgentSummary]:
        return [agent.summary for agent in _AGENTS]

    def process(self, request: ProcessingRequest) -> ProcessingRun:
        normalized = _normalize_input(request.content)
        fingerprint = _fingerprint(request, normalized)
        cached = self.store.get_by_fingerprint(fingerprint)
        if cached is not None:
            return cached

        project = _classify_project(normalized, request.project_hint)
        optional_agents = _route_optional_agents(normalized)
        agent_ids = (*_CORE_AGENT_IDS, *optional_agents)
        memory_matches = (
            tuple(
                self.store.search_memory(
                    query=normalized,
                    project=project,
                    limit=5,
                )
            )
            if "scout" in optional_agents
            else ()
        )
        input_tokens = max(1, math.ceil(len(normalized) / 4))
        costs = {
            agent_id: _estimate_agent_tokens(agent_id, input_tokens)
            for agent_id in agent_ids
        }
        allowed_agents, deferred_agents = _apply_budget(
            agent_ids,
            costs,
            request.token_budget,
        )
        intent = _primary_intent(optional_agents)
        context = _ProcessingContext(
            request=request,
            normalized=normalized,
            project=project,
            intent=intent,
            estimated_input_tokens=input_tokens,
            costs=costs,
            allowed_agents=allowed_agents,
            deferred_agents=deferred_agents,
            memory_matches=memory_matches,
        )
        steps = [self._run_agent(agent_id, context) for agent_id in agent_ids]
        artifacts = [
            artifact
            for step in steps
            for artifact in step.artifacts
        ]
        used_tokens = sum(
            step.estimated_tokens
            for step in steps
            if step.status != "deferred"
        )
        run = ProcessingRun(
            id=uuid4(),
            source=request.source,
            normalized_input=normalized,
            project=project,
            intent=intent,
            status=_run_status(steps),
            steps=steps,
            artifacts=artifacts,
            usage=UsageBudget(
                limit_tokens=request.token_budget,
                estimated_input_tokens=input_tokens,
                estimated_reserved_tokens=used_tokens,
                estimated_remaining_tokens=max(
                    0,
                    request.token_budget - used_tokens,
                ),
                deferred_agents=list(deferred_agents),
            ),
            created_at=datetime.now(UTC),
        )
        return self.store.save(fingerprint=fingerprint, run=run)

    def list_runs(self, *, limit: int = 100) -> list[ProcessingRun]:
        return self.store.list(limit=limit)

    def get_run(self, run_id: UUID) -> ProcessingRun | None:
        return self.store.get(run_id)

    def usage_summary(self) -> UsageSummary:
        return self.store.usage_summary()

    def list_projects(self) -> list[ProjectSummary]:
        return self.store.list_projects()

    def list_memory(
        self,
        *,
        project: str | None = None,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        return self.store.list_memory(project=project, limit=limit)

    def search_memory(
        self,
        *,
        query: str,
        project: str | None = None,
        limit: int = 20,
    ) -> list[MemoryRecord]:
        return self.store.search_memory(
            query=query,
            project=project,
            limit=limit,
        )

    def list_agent_tasks(
        self,
        *,
        project: str | None = None,
        task_status: AgentTaskStatus | None = None,
        limit: int = 100,
    ) -> list[AgentTaskRecord]:
        return self.store.list_agent_tasks(
            project=project,
            task_status=task_status,
            limit=limit,
        )

    def update_agent_task(
        self,
        task_id: UUID,
        *,
        task_status: AgentTaskStatus,
    ) -> AgentTaskRecord | None:
        return self.store.update_agent_task(
            task_id,
            task_status=task_status,
        )

    def dashboard(self) -> AgentDashboard:
        return self.store.dashboard()

    def _run_agent(
        self,
        agent_id: ProcessingAgentId,
        context: "_ProcessingContext",
    ) -> ProcessingStep:
        if agent_id in context.deferred_agents:
            return ProcessingStep(
                agent_id=agent_id,
                status="deferred",
                summary="Deferred by the Quartermaster to stay within budget.",
                estimated_tokens=0,
            )

        handlers = {
            "orchestrator": _orchestrator_step,
            "quartermaster": _quartermaster_step,
            "sentinel": _sentinel_step,
            "librarian": _librarian_step,
            "archivist": _archivist_step,
            "scout": _scout_step,
            "task-manager": _task_manager_step,
            "architect": _architect_step,
            "engineer": _engineer_step,
            "integrator": _integrator_step,
        }
        status, summary, artifacts = handlers[agent_id](context)
        return ProcessingStep(
            agent_id=agent_id,
            status=status,
            summary=summary,
            estimated_tokens=context.costs[agent_id],
            artifacts=artifacts,
        )


@dataclass(frozen=True, slots=True)
class _ProcessingContext:
    request: ProcessingRequest
    normalized: str
    project: str
    intent: str
    estimated_input_tokens: int
    costs: dict[ProcessingAgentId, int]
    allowed_agents: tuple[ProcessingAgentId, ...]
    deferred_agents: tuple[ProcessingAgentId, ...]
    memory_matches: tuple[MemoryRecord, ...]


def _normalize_input(content: str) -> str:
    normalized = " ".join(content.split())
    normalized = re.sub(
        r"\b([\w'-]+)(?:\s+\1\b)+",
        r"\1",
        normalized,
        flags=re.IGNORECASE,
    )
    return normalized.strip()


def _fingerprint(request: ProcessingRequest, normalized: str) -> str:
    payload = {
        "content": normalized.casefold(),
        "source": request.source,
        "project_hint": request.project_hint,
        "token_budget": request.token_budget,
        "external_access_allowed": request.external_access_allowed,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _classify_project(content: str, hint: str | None) -> str:
    if hint is not None:
        return hint
    lowered = content.casefold()
    for project, aliases in _PROJECT_PATTERNS:
        if any(alias in lowered for alias in aliases):
            return project
    return "Inbox"


def _route_optional_agents(
    content: str,
) -> tuple[ProcessingAgentId, ...]:
    lowered = content.casefold()
    return tuple(
        agent_id
        for agent_id, keywords in _OPTIONAL_KEYWORDS.items()
        if any(keyword in lowered for keyword in keywords)
    )


def _primary_intent(optional_agents: tuple[ProcessingAgentId, ...]) -> str:
    if "engineer" in optional_agents:
        return "build"
    if "integrator" in optional_agents:
        return "integrate"
    if "scout" in optional_agents:
        return "research"
    if "architect" in optional_agents:
        return "design"
    return "organize"


def _estimate_agent_tokens(
    agent_id: ProcessingAgentId,
    input_tokens: int,
) -> int:
    agent = _AGENT_BY_ID[agent_id]
    return agent.base_tokens + math.ceil(input_tokens * agent.input_ratio)


def _apply_budget(
    agent_ids: tuple[ProcessingAgentId, ...],
    costs: dict[ProcessingAgentId, int],
    budget: int,
) -> tuple[tuple[ProcessingAgentId, ...], tuple[ProcessingAgentId, ...]]:
    allowed: list[ProcessingAgentId] = []
    deferred: list[ProcessingAgentId] = []
    reserved = 0
    for agent_id in agent_ids:
        cost = costs[agent_id]
        if reserved + cost <= budget:
            allowed.append(agent_id)
            reserved += cost
        else:
            deferred.append(agent_id)
    return tuple(allowed), tuple(deferred)


def _run_status(steps: list[ProcessingStep]) -> ProcessingRunStatus:
    if any(step.status == "approval_required" for step in steps):
        return "needs_approval"
    if any(step.status == "deferred" for step in steps):
        return "partially_deferred"
    return "completed"


def _artifact(
    kind: ProcessingArtifactKind,
    title: str,
    **data: object,
) -> ProcessingArtifact:
    return ProcessingArtifact(kind=kind, title=title, data=data)


def _orchestrator_step(
    context: _ProcessingContext,
) -> tuple[AgentStepStatus, str, list[ProcessingArtifact]]:
    return (
        "completed",
        f"Normalized {context.request.source} intake and routed a {context.intent} run.",
        [
            _artifact(
                "normalized_input",
                "Normalized intake",
                content=context.normalized,
                source=context.request.source,
                tolerant_input=True,
            )
        ],
    )


def _quartermaster_step(
    context: _ProcessingContext,
) -> tuple[AgentStepStatus, str, list[ProcessingArtifact]]:
    reserved = sum(
        context.costs[agent_id]
        for agent_id in context.allowed_agents
    )
    return (
        "completed",
        f"Reserved {reserved} estimated tokens within a {context.request.token_budget} token budget.",
        [
            _artifact(
                "usage_plan",
                "Usage plan",
                estimated_input_tokens=context.estimated_input_tokens,
                allowed_agents=list(context.allowed_agents),
                deferred_agents=list(context.deferred_agents),
                provider_tokens_used=0,
                duplicate_runs_reused=True,
            )
        ],
    )


def _sentinel_step(
    context: _ProcessingContext,
) -> tuple[AgentStepStatus, str, list[ProcessingArtifact]]:
    matches = [
        pattern
        for pattern in _RISK_PATTERNS
        if re.search(pattern, context.normalized, flags=re.IGNORECASE)
    ]
    approval_required = bool(matches) and not context.request.external_access_allowed
    status: AgentStepStatus = (
        "approval_required" if approval_required else "completed"
    )
    summary = (
        "Effectful intent detected; execution requires explicit approval."
        if approval_required
        else "No unapproved high-impact execution was authorized."
    )
    return (
        status,
        summary,
        [
            _artifact(
                "security_note",
                "Security preflight",
                effectful_intent_detected=bool(matches),
                external_access_allowed=context.request.external_access_allowed,
                execution_performed=False,
                matched_rule_count=len(matches),
            )
        ],
    )


def _librarian_step(
    context: _ProcessingContext,
) -> tuple[AgentStepStatus, str, list[ProcessingArtifact]]:
    return (
        "completed",
        f"Filed the intake under {context.project}.",
        [
            _artifact(
                "project_classification",
                "Project classification",
                project=context.project,
                used_explicit_hint=context.request.project_hint is not None,
            )
        ],
    )


def _archivist_step(
    context: _ProcessingContext,
) -> tuple[AgentStepStatus, str, list[ProcessingArtifact]]:
    decisions = _matching_sentences(
        context.normalized,
        ("decide", "should", "use", "want", "will"),
    )
    return (
        "completed",
        "Prepared a durable memory note from the conversation.",
        [
            _artifact(
                "memory_note",
                "Conversation memory",
                project=context.project,
                summary=context.normalized[:500],
                decisions=decisions[:5],
            )
        ],
    )


def _scout_step(
    context: _ProcessingContext,
) -> tuple[AgentStepStatus, str, list[ProcessingArtifact]]:
    return (
        "completed",
        "Prepared a focused research handoff without performing external access.",
        [
            _artifact(
                "research_brief",
                "Research handoff",
                query=context.normalized[:500],
                external_access_performed=False,
                requires_source_citations=True,
                local_memory_matches=[
                    {
                        "id": str(record.id),
                        "project": record.project,
                        "kind": record.kind,
                        "content": record.content,
                    }
                    for record in context.memory_matches
                ],
            )
        ],
    )


def _task_manager_step(
    context: _ProcessingContext,
) -> tuple[AgentStepStatus, str, list[ProcessingArtifact]]:
    tasks = _extract_tasks(context.normalized)
    if not tasks:
        tasks = [context.normalized[:500]]
    return (
        "completed",
        f"Extracted {len(tasks)} actionable item(s).",
        [
            _artifact(
                "task",
                "Action items",
                project=context.project,
                items=tasks[:10],
                status="proposed",
            )
        ],
    )


def _architect_step(
    context: _ProcessingContext,
) -> tuple[AgentStepStatus, str, list[ProcessingArtifact]]:
    return (
        "completed",
        "Prepared the system-design handoff and kept execution boundaries explicit.",
        [
            _artifact(
                "architecture_brief",
                "Architecture handoff",
                goal=context.normalized[:500],
                boundary="planner-only; no target or connector execution",
                required_outputs=["data flow", "contracts", "security gates"],
            )
        ],
    )


def _engineer_step(
    context: _ProcessingContext,
) -> tuple[AgentStepStatus, str, list[ProcessingArtifact]]:
    return (
        "completed",
        "Prepared an implementation and verification handoff.",
        [
            _artifact(
                "implementation_brief",
                "Engineering handoff",
                goal=context.normalized[:500],
                project=context.project,
                required_outputs=["implementation", "tests", "verification"],
                execution_performed=False,
            )
        ],
    )


def _integrator_step(
    context: _ProcessingContext,
) -> tuple[AgentStepStatus, str, list[ProcessingArtifact]]:
    service_patterns = {
        "Box": r"\bbox\b(?!\s*brain\b)",
        "Calendar": r"\bcalendar\b",
        "Drive": r"\bdrive\b",
        "Email": r"\bemail\b",
        "Gmail": r"\bgmail\b",
        "GitHub": r"\bgithub\b",
        "Slack": r"\bslack\b",
    }
    services = [
        service
        for service, pattern in service_patterns.items()
        if re.search(pattern, context.normalized, flags=re.IGNORECASE)
    ]
    approval_required = bool(services) and not context.request.external_access_allowed
    status: AgentStepStatus = (
        "approval_required" if approval_required else "completed"
    )
    return (
        status,
        (
            "Prepared connector handoffs; external changes require approval."
            if approval_required
            else "Prepared an integration handoff without making external changes."
        ),
        [
            _artifact(
                "integration_request",
                "Integration handoff",
                services=services or ["unspecified"],
                external_access_allowed=context.request.external_access_allowed,
                external_change_performed=False,
            )
        ],
    )


def _matching_sentences(
    content: str,
    keywords: tuple[str, ...],
) -> list[str]:
    return [
        sentence
        for sentence in _sentences(content)
        if any(keyword in sentence.casefold() for keyword in keywords)
    ]


def _extract_tasks(content: str) -> list[str]:
    tasks: list[str] = []
    for sentence in _sentences(content):
        lowered = sentence.casefold()
        if any(
            re.search(rf"\b{re.escape(verb)}\b", lowered)
            for verb in _TASK_VERBS
        ):
            tasks.append(sentence)
    return tasks


def _sentences(content: str) -> list[str]:
    sentences = [
        sentence.strip(" -")
        for sentence in re.split(r"(?<=[.!?])\s+|\s*;\s*", content)
        if sentence.strip(" -")
    ]
    return sentences or [content]
