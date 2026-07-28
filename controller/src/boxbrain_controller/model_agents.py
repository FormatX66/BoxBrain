from __future__ import annotations

import importlib.util
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from .models import (
    ModelAgentPlan,
    ModelProcessingRun,
    ModelProviderUsage,
    ModelRuntimeStatus,
    ProcessingRequest,
)
from .processing_agents import ProcessingService


_AGENT_INSTRUCTIONS = """
You are the BoxBrain Orchestrator. Turn rough voice or chat intake into a precise,
grounded processing plan for the local BoxBrain crew.

Rules:
- Treat the supplied local classification and project as authoritative.
- Do not claim that you searched the web, changed files, sent messages, deployed,
  deleted, purchased, or performed any other external action.
- Use specialist_handoffs only for members of the supplied BoxBrain crew.
- Put concrete, independently actionable work in tasks and implementation_steps.
- Record only decisions that the user actually made; do not promote suggestions
  or assumptions into decisions.
- Put anything requiring an external change in integration_requests and set
  requires_approval to true.
- Set requires_approval when the local run requires approval or when the plan
  proposes sending, publishing, deploying, deleting, purchasing, transferring,
  credential access, or device control.
- Keep every string concise and return only the typed output.
""".strip()


class ModelAgentRuntimeUnavailable(RuntimeError):
    """The optional provider-backed agent runtime is not ready."""


class ModelAgentExecutionError(RuntimeError):
    """The provider-backed agent run did not complete successfully."""

    def __init__(self, message: str, *, category: str = "provider") -> None:
        super().__init__(message)
        self.category = category


@dataclass(frozen=True, slots=True)
class AgentRunnerResult:
    plan: ModelAgentPlan
    usage: ModelProviderUsage


class AgentRunner(Protocol):
    async def run(self, prompt: str) -> AgentRunnerResult: ...


class OpenAIAgentRunner:
    """Small adapter around the OpenAI Agents SDK."""

    def __init__(self, *, model: str, max_output_tokens: int) -> None:
        self.model = model
        self.max_output_tokens = max_output_tokens

    async def run(self, prompt: str) -> AgentRunnerResult:
        try:
            from agents import Agent, ModelSettings, Runner
            from openai.types.shared import Reasoning
        except ImportError as error:
            raise ModelAgentRuntimeUnavailable(
                "The OpenAI Agents SDK is not installed."
            ) from error

        agent = Agent(
            name="BoxBrain Orchestrator",
            instructions=_AGENT_INSTRUCTIONS,
            model=self.model,
            model_settings=ModelSettings(
                reasoning=Reasoning(effort="medium"),
                verbosity="low",
                max_tokens=self.max_output_tokens,
                store=False,
            ),
            output_type=ModelAgentPlan,
        )
        try:
            result = await Runner.run(agent, prompt, max_turns=1)
        except Exception as error:
            raise _provider_execution_error(error) from error

        try:
            plan = ModelAgentPlan.model_validate(result.final_output)
            provider_usage = result.context_wrapper.usage
            usage = ModelProviderUsage(
                requests=provider_usage.requests,
                input_tokens=provider_usage.input_tokens,
                output_tokens=provider_usage.output_tokens,
                total_tokens=provider_usage.total_tokens,
            )
        except Exception as error:
            raise ModelAgentExecutionError(
                "The model provider returned an invalid agent result."
            ) from error
        return AgentRunnerResult(plan=plan, usage=usage)


class ModelAgentService:
    """Provider-backed reasoning layered over the durable local processing crew."""

    def __init__(
        self,
        local_service: ProcessingService,
        *,
        enabled: bool,
        model: str,
        max_output_tokens: int,
        runner: AgentRunner | None = None,
    ) -> None:
        self.local_service = local_service
        self.store = local_service.store
        self.enabled = enabled
        self.model = model
        self.max_output_tokens = max_output_tokens
        self._runner_override = runner

    def runtime_status(self) -> ModelRuntimeStatus:
        configured = bool(self._runner_override) or bool(
            os.getenv("OPENAI_API_KEY")
        )
        sdk_available = bool(self._runner_override) or (
            importlib.util.find_spec("agents") is not None
        )
        return ModelRuntimeStatus(
            enabled=self.enabled,
            configured=configured,
            sdk_available=sdk_available,
            ready=self.enabled and configured and sdk_available,
            model=self.model,
        )

    async def process(self, request: ProcessingRequest) -> ModelProcessingRun:
        self._require_ready()
        local_run = self.local_service.process(request)
        cached = self.store.get_model_run_for_local(
            local_run.id,
            model=self.model,
        )
        if cached is not None:
            return cached

        prior_memory = [
            memory
            for memory in self.local_service.search_memory(
                query=request.content,
                project=local_run.project,
                limit=6,
            )
            if memory.source_run_id != local_run.id
        ]
        runner = self._runner_override or OpenAIAgentRunner(
            model=self.model,
            max_output_tokens=self.max_output_tokens,
        )
        runner_result = await runner.run(
            _build_prompt(
                request=request,
                local_run=local_run.model_dump(mode="json"),
                prior_memory=[
                    {
                        "kind": memory.kind,
                        "content": memory.content[:500],
                    }
                    for memory in prior_memory
                ],
            )
        )
        plan = _ground_plan(
            runner_result.plan,
            project=local_run.project,
            local_requires_approval=local_run.status == "needs_approval",
        )
        model_run = ModelProcessingRun(
            id=uuid4(),
            local_run=local_run,
            plan=plan,
            model=self.model,
            usage=runner_result.usage,
            created_at=datetime.now(UTC),
        )
        return self.store.save_model_run(model_run)

    def get_run(self, run_id: UUID) -> ModelProcessingRun | None:
        return self.store.get_model_run(run_id)

    def list_runs(self, *, limit: int = 100) -> list[ModelProcessingRun]:
        return self.store.list_model_runs(limit=limit)

    def _require_ready(self) -> None:
        status = self.runtime_status()
        if not status.enabled:
            raise ModelAgentRuntimeUnavailable(
                "The model-agent runtime is disabled."
            )
        if not status.configured:
            raise ModelAgentRuntimeUnavailable(
                "OPENAI_API_KEY is not configured for the controller."
            )
        if not status.sdk_available:
            raise ModelAgentRuntimeUnavailable(
                "The OpenAI Agents SDK is not installed."
            )


def _build_prompt(
    *,
    request: ProcessingRequest,
    local_run: dict[str, object],
    prior_memory: list[dict[str, str]],
) -> str:
    content_limit = max(512, min(20_000, request.token_budget * 4))
    payload = {
        "intake": request.content[:content_limit],
        "source": request.source,
        "project_hint": request.project_hint,
        "external_access_allowed": request.external_access_allowed,
        "local_run": {
            "project": local_run["project"],
            "intent": local_run["intent"],
            "status": local_run["status"],
            "steps": [
                {
                    "agent_id": step["agent_id"],
                    "status": step["status"],
                    "summary": step["summary"],
                }
                for step in local_run["steps"]
            ],
        },
        "prior_local_memory": prior_memory,
    }
    return (
        "Create the typed BoxBrain processing plan from this JSON context. "
        "Ground the plan only in the supplied context:\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    )


def _ground_plan(
    plan: ModelAgentPlan,
    *,
    project: str,
    local_requires_approval: bool,
) -> ModelAgentPlan:
    return plan.model_copy(
        update={
            "project": project,
            "requires_approval": (
                plan.requires_approval or local_requires_approval
            ),
        }
    )

def _provider_execution_error(error: Exception) -> ModelAgentExecutionError:
    status_code = getattr(error, "status_code", None)
    error_code = getattr(error, "code", None)
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        error_code = error_code or body.get("code")
        nested = body.get("error")
        if isinstance(nested, dict):
            error_code = error_code or nested.get("code")

    if error_code == "insufficient_quota":
        return ModelAgentExecutionError(
            "OpenAI API quota is unavailable; check API billing or limits.",
            category="quota",
        )
    if status_code == 401 or error_code == "invalid_api_key":
        return ModelAgentExecutionError(
            "OpenAI API authentication failed.",
            category="authentication",
        )
    if status_code == 403 or error_code == "model_not_found":
        return ModelAgentExecutionError(
            "The API project cannot access the configured model.",
            category="access",
        )
    if status_code == 429:
        return ModelAgentExecutionError(
            "OpenAI API rate limit reached; retry later.",
            category="rate_limit",
        )
    return ModelAgentExecutionError("The model provider request failed.")
