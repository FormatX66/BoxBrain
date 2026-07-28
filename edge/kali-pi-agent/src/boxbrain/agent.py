"""Policy-first state for the BoxBrain Kali Pi edge agent."""

from __future__ import annotations

import hashlib
import os
from typing import Any

from boxbrain.links import load_links


BUILTIN_CAPABILITIES = (
    {
        "id": "system-observation",
        "name": "System observation",
        "domain": "operations",
        "mode": "automatic-read-only",
        "status": "ready",
        "description": "Collects health baselines from explicitly authorized targets.",
    },
    {
        "id": "network-assessment",
        "name": "Network security assessment",
        "domain": "security",
        "mode": "authorization-required",
        "status": "ready",
        "description": "Inventories authorized private networks and records evidence.",
    },
    {
        "id": "optimization-planning",
        "name": "Optimization planning",
        "domain": "optimization",
        "mode": "advisory",
        "status": "ready",
        "description": "Turns system measurements into prioritized optimization proposals.",
    },
    {
        "id": "repair-guidance",
        "name": "Repair guidance",
        "domain": "repair",
        "mode": "advisory",
        "status": "ready",
        "description": "Explains repair risks and safe next steps in plain language.",
    },
    {
        "id": "approved-actions",
        "name": "Approved action execution",
        "domain": "automation",
        "mode": "explicit-approval",
        "status": "guarded",
        "description": "Reserved for reversible, logged actions approved by the operator.",
    },
    {
        "id": "ai-reasoning",
        "name": "AI reasoning provider",
        "domain": "intelligence",
        "mode": "advisory",
        "status": "provider-not-configured",
        "description": "Future reasoning provider for explanations, planning, and coordination.",
    },
)


def _recommendation_id(address: str, title: str) -> str:
    digest = hashlib.sha256(f"{address}\0{title}".encode("utf-8")).hexdigest()
    return digest[:16]


def _domain(title: str) -> str:
    lowered = title.lower()
    if "disk" in lowered or "space" in lowered or "memory" in lowered:
        return "optimization"
    if "network" in lowered or "device" in lowered:
        return "repair"
    if "restart" in lowered or "reboot" in lowered:
        return "operations"
    return "system"


def recommendations(
    links: list[dict[str, Any]],
    latest_assessment: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for link in links:
        address = str(link.get("address", "unknown"))
        hostname = str(link.get("hostname", address))
        diagnostic = link.get("diagnostics")
        if not isinstance(diagnostic, dict) or diagnostic.get("status") != "completed":
            title = "Complete the system intelligence baseline"
            items.append(
                {
                    "id": _recommendation_id(address, title),
                    "target": hostname,
                    "address": address,
                    "domain": "operations",
                    "priority": "normal",
                    "title": title,
                    "reason": "The target is authorized, but a complete health baseline is not available.",
                    "proposed_action": "Retry read-only diagnostics when the target is stable.",
                    "execution": "automatic-read-only",
                    "requires_approval": False,
                }
            )
            continue

        findings = diagnostic.get("findings", [])
        if not isinstance(findings, list):
            findings = []
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            title = str(finding.get("title", "Review target finding"))
            severity = str(finding.get("severity", "low"))
            items.append(
                {
                    "id": _recommendation_id(address, title),
                    "target": hostname,
                    "address": address,
                    "domain": _domain(title),
                    "priority": (
                        "urgent"
                        if severity in {"critical", "high"}
                        else "normal"
                        if severity == "medium"
                        else "low"
                    ),
                    "title": title,
                    "reason": str(finding.get("detail", "BoxBrain identified a condition to review.")),
                    "proposed_action": str(
                        finding.get("recommendation", "Review the condition before changing the system.")
                    ),
                    "execution": "operator-approved",
                    "requires_approval": True,
                }
            )

        if not findings:
            title = "Maintain the current healthy baseline"
            items.append(
                {
                    "id": _recommendation_id(address, title),
                    "target": hostname,
                    "address": address,
                    "domain": "optimization",
                    "priority": "low",
                    "title": title,
                    "reason": "The latest read-only system baseline produced no health findings.",
                    "proposed_action": "Continue monitoring and compare future baselines for change.",
                    "execution": "automatic-read-only",
                    "requires_approval": False,
                }
            )

    if latest_assessment and int(latest_assessment.get("finding_count", 0) or 0) > 0:
        title = "Review the latest network security findings"
        items.append(
            {
                "id": _recommendation_id("network", title),
                "target": str(latest_assessment.get("target", "authorized network")),
                "address": None,
                "domain": "security",
                "priority": "normal",
                "title": title,
                "reason": (
                    f"The latest assessment contains "
                    f"{latest_assessment.get('finding_count', 0)} finding(s)."
                ),
                "proposed_action": "Review the evidence report and approve remediation separately.",
                "execution": "operator-approved",
                "requires_approval": True,
            }
        )

    priority_rank = {"urgent": 0, "normal": 1, "low": 2}
    return sorted(
        items,
        key=lambda item: (
            priority_rank.get(str(item.get("priority")), 9),
            str(item.get("target")),
            str(item.get("title")),
        ),
    )


def agent_state(
    state_directory: str,
    latest_assessment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    links = load_links(state_directory)
    capability_items = [dict(item) for item in BUILTIN_CAPABILITIES]
    ai_provider = os.environ.get("BOXBRAIN_AI_PROVIDER", "").strip()
    if ai_provider:
        for capability in capability_items:
            if capability["id"] == "ai-reasoning":
                capability["status"] = "configured"
                capability["provider"] = ai_provider
                break
    recommendation_items = recommendations(links, latest_assessment)
    return {
        "name": "BoxBrain Kali Pi Edge Agent",
        "role": "edge-agent",
        "operating_mode": os.environ.get(
            "BOXBRAIN_AGENT_MODE",
            os.environ.get("BOXBRAIN_CONTROLLER_MODE", "advisory"),
        ),
        "reasoning_provider": ai_provider or "not-configured",
        "policy": {
            "observe": "automatic-on-authorized-targets",
            "recommend": "automatic",
            "change": "explicit-approval-required",
            "destructive_actions": "disabled",
        },
        "target_count": len(links),
        "capabilities": capability_items,
        "recommendation_count": len(recommendation_items),
        "recommendations": recommendation_items,
    }
