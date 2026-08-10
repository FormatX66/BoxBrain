from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from .copilot_offload import (
    GITHUB_COPILOT_SEND_CONFIRMATION,
    CopilotOffloadService,
    CopilotProvider,
    CopilotProviderRuntime,
    CopilotTaskKind,
)
from .script_first import RouteDecision, RouteRequest, ScriptFirstService, TaskRoute


class WorkflowLane(StrEnum):
    LOCAL_SCRIPT = "local_script"
    GITHUB_COPILOT = "github_copilot"
    HYBRID_GITHUB_COPILOT = "hybrid_github_copilot"
    WINDOWS_COPILOT_MANUAL = "windows_copilot_manual"
    GPT = "gpt"
    HUMAN_REVIEW = "human_review"


class WorkflowOptimizeRequest(RouteRequest):
    copilot_kind: CopilotTaskKind | None = None
    preferred_provider: CopilotProvider | None = None


class WorkflowStep(BaseModel):
    sequence: int = Field(ge=1)
    lane: WorkflowLane
    action: str
    effect: Literal["local_read", "external_plan", "manual", "review"]
    automatic: bool = False
    requires_confirmation: bool = False


class WorkflowPlan(BaseModel):
    task_id: str | None
    route: RouteDecision
    selected_lane: WorkflowLane
    provider: CopilotProvider | None
    provider_display_name: str | None
    provider_installed: bool | None
    dispatch_mode: Literal["guarded_automation", "manual_only"] | None
    dispatch_available: bool
    confirmation_phrase: str | None
    human_review_required: bool
    estimated_external_model_calls: int = Field(ge=0, le=1)
    reasons: tuple[str, ...]
    steps: tuple[WorkflowStep, ...]
    action_taken: bool = False


class WorkflowOptimizerService:
    """Recommend a provider-aware workflow without executing or dispatching it."""

    def __init__(
        self,
        script_first_service: ScriptFirstService,
        copilot_offload_service: CopilotOffloadService,
    ) -> None:
        self.script_first_service = script_first_service
        self.copilot_offload_service = copilot_offload_service

    def optimize(self, request: WorkflowOptimizeRequest) -> WorkflowPlan:
        route_request = RouteRequest.model_validate(
            {
                field_name: getattr(request, field_name)
                for field_name in RouteRequest.model_fields
            }
        )
        route = self.script_first_service.classify(route_request)

        if request.high_impact or request.destructive:
            return WorkflowPlan(
                task_id=request.task_id,
                route=route,
                selected_lane=WorkflowLane.HUMAN_REVIEW,
                provider=None,
                provider_display_name=None,
                provider_installed=None,
                dispatch_mode=None,
                dispatch_available=False,
                confirmation_phrase=None,
                human_review_required=True,
                estimated_external_model_calls=0,
                reasons=(
                    "High-impact or destructive work cannot be delegated to either "
                    "Copilot provider.",
                    "Keep execution behind BoxBrain's local policy and approval controls.",
                ),
                steps=(
                    WorkflowStep(
                        sequence=1,
                        lane=WorkflowLane.HUMAN_REVIEW,
                        action="Review scope, rollback, and exact local approval requirements.",
                        effect="review",
                    ),
                ),
            )

        if route.route is TaskRoute.SCRIPT:
            return WorkflowPlan(
                task_id=request.task_id,
                route=route,
                selected_lane=WorkflowLane.LOCAL_SCRIPT,
                provider=None,
                provider_display_name=None,
                provider_installed=None,
                dispatch_mode=None,
                dispatch_available=False,
                confirmation_phrase=None,
                human_review_required=route.human_review_required,
                estimated_external_model_calls=0,
                reasons=(
                    "A registered deterministic script is the lowest-cost reliable workflow.",
                    "No Copilot provider or external model call is needed.",
                ),
                steps=(
                    WorkflowStep(
                        sequence=1,
                        lane=WorkflowLane.LOCAL_SCRIPT,
                        action=(
                            f"Run registered script '{request.script_id}' through the "
                            "script-runs endpoint."
                        ),
                        effect="local_read",
                    ),
                    WorkflowStep(
                        sequence=2,
                        lane=WorkflowLane.LOCAL_SCRIPT,
                        action=(
                            "Verify the structured result and reuse its idempotency key "
                            "on retries."
                        ),
                        effect="review",
                    ),
                ),
            )

        if request.preferred_provider is CopilotProvider.WINDOWS_COPILOT_APP:
            windows = self._provider(CopilotProvider.WINDOWS_COPILOT_APP)
            return self._windows_manual_plan(request, route, windows)

        if request.copilot_kind is not None:
            github = self._provider(CopilotProvider.GITHUB_COPILOT_CLI)
            return self._github_plan(request, route, github)

        return self._generic_model_plan(request, route)

    def _github_plan(
        self,
        request: WorkflowOptimizeRequest,
        route: RouteDecision,
        provider: CopilotProviderRuntime,
    ) -> WorkflowPlan:
        local_preprocessing = route.script_available
        lane = (
            WorkflowLane.HYBRID_GITHUB_COPILOT
            if local_preprocessing
            else WorkflowLane.GITHUB_COPILOT
        )
        steps: list[WorkflowStep] = []
        if local_preprocessing:
            steps.append(
                WorkflowStep(
                    sequence=1,
                    lane=WorkflowLane.LOCAL_SCRIPT,
                    action=(
                        f"Run registered script '{request.script_id}' first to bound the evidence "
                        "sent for reasoning."
                    ),
                    effect="local_read",
                )
            )
        steps.extend(
            (
                WorkflowStep(
                    sequence=len(steps) + 1,
                    lane=lane,
                    action=(
                        f"Prepare a minimal {request.copilot_kind.value} packet labeled "
                        "github-copilot-cli."
                    ),
                    effect="local_read",
                ),
                WorkflowStep(
                    sequence=len(steps) + 2,
                    lane=lane,
                    action="Review included paths, exclusions, content bytes, and prompt hash.",
                    effect="review",
                    requires_confirmation=True,
                ),
                WorkflowStep(
                    sequence=len(steps) + 3,
                    lane=lane,
                    action="Dispatch only after the exact GitHub-specific confirmation.",
                    effect="external_plan",
                    requires_confirmation=True,
                ),
                WorkflowStep(
                    sequence=len(steps) + 4,
                    lane=lane,
                    action=(
                        "Treat the response as untrusted; review, test, and apply locally "
                        "if accepted."
                    ),
                    effect="review",
                ),
            )
        )
        reasons = [
            "The task declares a bounded Copilot task kind supported by GitHub Copilot CLI.",
            "Microsoft Copilot for Windows is not an automated workflow target.",
        ]
        if local_preprocessing:
            reasons.insert(0, "A registered local script can reduce the external reasoning scope.")
        if not provider.installed:
            reasons.append("GitHub Copilot CLI is not installed, so dispatch is unavailable.")
        elif not provider.dispatch_available:
            reasons.append("GitHub Copilot dispatch remains disabled until an approved send.")
        return WorkflowPlan(
            task_id=request.task_id,
            route=route,
            selected_lane=lane,
            provider=provider.provider,
            provider_display_name=provider.display_name,
            provider_installed=provider.installed,
            dispatch_mode=provider.dispatch_mode,
            dispatch_available=provider.dispatch_available,
            confirmation_phrase=GITHUB_COPILOT_SEND_CONFIRMATION,
            human_review_required=True,
            estimated_external_model_calls=1,
            reasons=tuple(reasons),
            steps=tuple(steps),
        )

    @staticmethod
    def _windows_manual_plan(
        request: WorkflowOptimizeRequest,
        route: RouteDecision,
        provider: CopilotProviderRuntime,
    ) -> WorkflowPlan:
        reasons = [
            "Microsoft Copilot for Windows was explicitly requested as a separate manual surface.",
            "BoxBrain does not automate its UI or assume a local prompt API.",
        ]
        if not provider.installed:
            reasons.append("The Microsoft Copilot Windows app is not detected for this user.")
        return WorkflowPlan(
            task_id=request.task_id,
            route=route,
            selected_lane=WorkflowLane.WINDOWS_COPILOT_MANUAL,
            provider=provider.provider,
            provider_display_name=provider.display_name,
            provider_installed=provider.installed,
            dispatch_mode=provider.dispatch_mode,
            dispatch_available=False,
            confirmation_phrase=None,
            human_review_required=True,
            estimated_external_model_calls=1,
            reasons=tuple(reasons),
            steps=(
                WorkflowStep(
                    sequence=1,
                    lane=WorkflowLane.WINDOWS_COPILOT_MANUAL,
                    action=(
                        "Prepare and review a minimal text prompt without automatically "
                        "attaching files."
                    ),
                    effect="local_read",
                ),
                WorkflowStep(
                    sequence=2,
                    lane=WorkflowLane.WINDOWS_COPILOT_MANUAL,
                    action=(
                        "Open Microsoft Copilot for Windows and copy the reviewed text "
                        "manually."
                    ),
                    effect="manual",
                ),
                WorkflowStep(
                    sequence=3,
                    lane=WorkflowLane.WINDOWS_COPILOT_MANUAL,
                    action=(
                        "Validate the response locally; never treat it as an executable "
                        "instruction."
                    ),
                    effect="review",
                ),
            ),
        )

    @staticmethod
    def _generic_model_plan(
        request: WorkflowOptimizeRequest,
        route: RouteDecision,
    ) -> WorkflowPlan:
        lane = WorkflowLane.GPT
        reasons = [
            "No supported Copilot task kind or explicit Windows Copilot preference was supplied.",
            "Use the existing bounded GPT reasoning lane selected by the script-first router.",
        ]
        steps: list[WorkflowStep] = []
        if route.script_available:
            steps.append(
                WorkflowStep(
                    sequence=1,
                    lane=WorkflowLane.LOCAL_SCRIPT,
                    action=(
                        f"Run registered script '{request.script_id}' to collect bounded "
                        "local evidence."
                    ),
                    effect="local_read",
                )
            )
        steps.append(
            WorkflowStep(
                sequence=len(steps) + 1,
                lane=lane,
                action="Run one bounded model reasoning pass and review its proposed workflow.",
                effect="external_plan",
            )
        )
        return WorkflowPlan(
            task_id=request.task_id,
            route=route,
            selected_lane=lane,
            provider=None,
            provider_display_name=None,
            provider_installed=None,
            dispatch_mode=None,
            dispatch_available=False,
            confirmation_phrase=None,
            human_review_required=route.human_review_required,
            estimated_external_model_calls=1,
            reasons=tuple(reasons),
            steps=tuple(steps),
        )

    def _provider(self, provider_id: CopilotProvider) -> CopilotProviderRuntime:
        return next(
            provider
            for provider in self.copilot_offload_service.runtime_status().providers
            if provider.provider is provider_id
        )
