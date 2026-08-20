from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable, Mapping, Sequence

from capacity_mesh import AssignmentPlan, Node, WorkItem, assign_parallel


AUTHORITY_LEVELS = frozenset({"BUILD-ONLY", "VERIFY-ONLY", "PHYSICAL-EVIDENCE", "PROMOTION"})
EXTERNAL_PROVIDERS = frozenset({"circleci-verifier", "gcp-burst", "oci-arm", "contributor-fork"})
REQUIRED_PROVIDERS = frozenset(
    {
        "github-x64",
        "github-arm64",
        "circleci-verifier",
        "gcp-burst",
        "oci-arm",
        "contributor-fork",
        "hopper-physical",
        "bbpi4-physical",
        "aurum-convergence",
    }
)


@dataclass(frozen=True)
class ProviderMetrics:
    observations: int = 0
    queue_wait_seconds: float = 0.0
    startup_delay_seconds: float = 0.0
    cache_hit_rate: float = 0.0
    execution_seconds: float = 0.0
    artifact_transfer_seconds: float = 0.0
    failure_rate: float = 0.0
    verification_usefulness: float = 0.0
    free_tier_fraction: float = 0.0

    @property
    def critical_path_seconds(self) -> float:
        return (
            self.queue_wait_seconds
            + self.startup_delay_seconds
            + self.execution_seconds
            + self.artifact_transfer_seconds
        )


@dataclass(frozen=True)
class ProviderDecision:
    plan: AssignmentPlan
    excluded: Mapping[str, str]


def metrics_from_policy(policy: Mapping[str, Any]) -> dict[str, ProviderMetrics]:
    out: dict[str, ProviderMetrics] = {}
    for name, raw in policy.get("provider_metrics", {}).items():
        out[str(name)] = ProviderMetrics(
            observations=max(0, int(raw.get("observations", 0))),
            queue_wait_seconds=max(0.0, float(raw.get("queue_wait_seconds", 0))),
            startup_delay_seconds=max(0.0, float(raw.get("startup_delay_seconds", 0))),
            cache_hit_rate=min(1.0, max(0.0, float(raw.get("cache_hit_rate", 0)))),
            execution_seconds=max(0.0, float(raw.get("execution_seconds", 0))),
            artifact_transfer_seconds=max(0.0, float(raw.get("artifact_transfer_seconds", 0))),
            failure_rate=min(1.0, max(0.0, float(raw.get("failure_rate", 0)))),
            verification_usefulness=min(1.0, max(0.0, float(raw.get("verification_usefulness", 0)))),
            free_tier_fraction=max(0.0, float(raw.get("free_tier_fraction", 0))),
        )
    return out


def provider_is_helpful(
    metrics: ProviderMetrics,
    *,
    baseline_critical_path_seconds: float,
    minimum_observations: int = 3,
) -> bool:
    if metrics.free_tier_fraction >= 1.0:
        return False
    if metrics.observations < minimum_observations:
        return True
    adds_independent_evidence = metrics.verification_usefulness >= 0.5 and metrics.failure_rate < 0.5
    shortens_path = (
        metrics.critical_path_seconds < baseline_critical_path_seconds
        and metrics.failure_rate <= 0.25
        and metrics.free_tier_fraction <= 1.0
    )
    return adds_independent_evidence or shortens_path


def select_providers(
    work: Sequence[WorkItem],
    nodes: Sequence[Node],
    *,
    metrics: Mapping[str, ProviderMetrics] | None = None,
    baseline_critical_path_seconds: float = 0.0,
) -> ProviderDecision:
    observed = metrics or {}
    usable: list[Node] = []
    excluded: dict[str, str] = {}
    for node in nodes:
        if not node.available:
            excluded[node.name] = "unavailable"
            continue
        node_metrics = observed.get(node.name, ProviderMetrics())
        if node.optional and baseline_critical_path_seconds > 0 and not provider_is_helpful(
            node_metrics,
            baseline_critical_path_seconds=baseline_critical_path_seconds,
        ):
            excluded[node.name] = "does-not-shorten-path-or-add-useful-evidence"
            continue
        if node_metrics.observations:
            usable.append(
                replace(
                    node,
                    expected_queue_seconds=round(node_metrics.queue_wait_seconds + node_metrics.startup_delay_seconds),
                    estimated_runtime_seconds=round(
                        node_metrics.execution_seconds + node_metrics.artifact_transfer_seconds
                    ),
                    cache_locality=node_metrics.cache_hit_rate,
                )
            )
        else:
            usable.append(node)
    return ProviderDecision(assign_parallel(work, usable), excluded)


def validate_provider_policy(policy: Mapping[str, Any]) -> None:
    nodes = {str(node["name"]): node for node in policy.get("nodes", ())}
    missing = REQUIRED_PROVIDERS - nodes.keys()
    if missing:
        raise ValueError(f"provider policy is missing: {sorted(missing)}")
    for name in EXTERNAL_PROVIDERS:
        node = nodes[name]
        authorities = set(node.get("authority_levels", ())) | {str(node.get("authority_level", ""))}
        if "PROMOTION" in authorities:
            raise ValueError(f"external provider has promotion authority: {name}")
        if not node.get("optional", False):
            raise ValueError(f"external provider must be optional: {name}")
    if nodes["aurum-convergence"].get("authority_level") != "PROMOTION":
        raise ValueError("Aurum convergence must retain sole promotion authority")
    if nodes["oci-arm"].get("authority_level") == "PHYSICAL-EVIDENCE":
        raise ValueError("OCI ARM must not impersonate physical Pi evidence")
    if nodes["bbpi4-physical"].get("authority_level") != "PHYSICAL-EVIDENCE":
        raise ValueError("BBPI4 must remain physical evidence")
    if nodes["hopper-physical"].get("physical_priority") != "PRIMARY-x86":
        raise ValueError("Hopper must remain the primary x86 physical node")


def available_nodes(policy: Mapping[str, Any], names: Iterable[str]) -> tuple[Node, ...]:
    from mesh_efficiency import nodes_from_policy

    validate_provider_policy(policy)
    return nodes_from_policy(policy, available=set(names))


__all__ = [
    "AUTHORITY_LEVELS",
    "EXTERNAL_PROVIDERS",
    "ProviderDecision",
    "ProviderMetrics",
    "available_nodes",
    "metrics_from_policy",
    "provider_is_helpful",
    "select_providers",
    "validate_provider_policy",
]
