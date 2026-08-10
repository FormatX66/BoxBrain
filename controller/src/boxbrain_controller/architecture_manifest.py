from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


ArchitectureAgentMaturity = Literal["operational", "foundation", "planned"]
ArchitectureAgentBoundary = Literal[
    "planner",
    "local-control-plane",
    "operator-guided",
    "transport",
]


class ArchitectureAgent(BaseModel):
    id: str
    name: str
    mission: str
    responsibilities: tuple[str, ...]
    boundary: ArchitectureAgentBoundary
    maturity: ArchitectureAgentMaturity
    compatibility_components: tuple[str, ...] = ()


class ArchitectureManifest(BaseModel):
    version: Literal["1.1"] = "1.1"
    name: Literal["BoxBrain Master Architecture"] = "BoxBrain Master Architecture"
    interface: Literal["Arkmatx Interface"] = "Arkmatx Interface"
    flow: tuple[str, ...]
    principles: tuple[str, ...]
    agents: tuple[ArchitectureAgent, ...]
    compatibility_notes: tuple[str, ...]


_AGENTS = (
    ArchitectureAgent(
        id="orchestrator",
        name="Orchestrator",
        mission="Coordinate every operation inside BoxBrain.",
        responsibilities=(
            "understand goals",
            "build execution plans",
            "route specialist work",
            "track dependencies and approvals",
            "produce final reports",
        ),
        boundary="planner",
        maturity="operational",
        compatibility_components=("processing orchestrator",),
    ),
    ArchitectureAgent(
        id="knowledge-manager",
        name="Knowledge Manager",
        mission="Maintain canonical documentation and project knowledge.",
        responsibilities=("documentation", "reference material", "summaries"),
        boundary="planner",
        maturity="operational",
        compatibility_components=("Archivist", "project memory"),
    ),
    ArchitectureAgent(
        id="memory-manager",
        name="Memory Manager",
        mission="Maintain long-term project continuity.",
        responsibilities=("milestones", "persistent summaries", "context handoffs"),
        boundary="local-control-plane",
        maturity="operational",
        compatibility_components=("processing store", "memory search"),
    ),
    ArchitectureAgent(
        id="task-manager",
        name="Task Manager",
        mission="Convert goals into prioritized, dependency-aware work.",
        responsibilities=("task extraction", "priorities", "dependencies", "roadmaps"),
        boundary="planner",
        maturity="operational",
        compatibility_components=("Dispatcher", "task store"),
    ),
    ArchitectureAgent(
        id="repository-manager",
        name="Repository Manager",
        mission="Manage source repositories through reviewable operations.",
        responsibilities=("clone", "pull", "branch", "push", "merge", "health"),
        boundary="operator-guided",
        maturity="planned",
    ),
    ArchitectureAgent(
        id="website-manager",
        name="Website Manager",
        mission="Build and maintain versioned websites and assets.",
        responsibilities=("generate", "update", "manage assets", "publish builds"),
        boundary="operator-guided",
        maturity="planned",
    ),
    ArchitectureAgent(
        id="deployment-manager",
        name="Deployment Manager",
        mission="Package and deploy applications with rollback.",
        responsibilities=("build", "package", "deploy", "rollback", "release"),
        boundary="operator-guided",
        maturity="planned",
    ),
    ArchitectureAgent(
        id="diagnostics-manager",
        name="Diagnostics Manager",
        mission="Analyze bounded system health evidence and recommend fixes.",
        responsibilities=("health", "logs", "failure analysis", "recommendations"),
        boundary="local-control-plane",
        maturity="operational",
        compatibility_components=("AI diagnostic executor", "Kali Pi edge agent"),
    ),
    ArchitectureAgent(
        id="fleet-manager",
        name="Fleet Manager",
        mission="Maintain inventory and status for connected machines.",
        responsibilities=("inventory", "status", "resource tracking", "search"),
        boundary="local-control-plane",
        maturity="foundation",
        compatibility_components=("remote target manager", "FleetService"),
    ),
    ArchitectureAgent(
        id="machine-provisioning-agent",
        name="Machine Provisioning Agent",
        mission="Guide safe, resumable onboarding for one machine identity.",
        responsibilities=(
            "identity",
            "account setup guidance",
            "software checklist",
            "registration",
            "provisioning report",
        ),
        boundary="operator-guided",
        maturity="foundation",
        compatibility_components=("FleetService provisioning workflow",),
    ),
    ArchitectureAgent(
        id="brain-connect",
        name="Brain Connect",
        mission="Provide secure, capability-scoped machine communication.",
        responsibilities=(
            "command routing",
            "file synchronization",
            "heartbeat",
            "secure transport",
        ),
        boundary="transport",
        maturity="foundation",
        compatibility_components=("remote target manager", "edge agent"),
    ),
    ArchitectureAgent(
        id="capability-registry",
        name="Capability Registry",
        mission="Catalog machine and agent capabilities.",
        responsibilities=("hardware", "software", "tools", "agent capabilities"),
        boundary="local-control-plane",
        maturity="foundation",
        compatibility_components=("FleetService capability inventory",),
    ),
)


def get_architecture_manifest() -> ArchitectureManifest:
    return ArchitectureManifest(
        flow=(
            "Bruce (User)",
            "Arkmatx Interface",
            "BoxBrain (AI Orchestrator)",
            "Specialized Agents",
            "Brain Connect",
            "Authorized Machine / VM / Raspberry Pi / Cloud Service",
        ),
        principles=(
            "modular",
            "replaceable",
            "extensible",
            "versioned",
            "documented",
            "testable",
            "recoverable",
            "configurable",
            "logged",
        ),
        agents=_AGENTS,
        compatibility_notes=(
            "The existing ten-agent processing crew remains unchanged.",
            "Remote sessions and AI diagnostics retain their existing approval gates.",
            "External account creation is operator-guided; BoxBrain stores no passwords.",
            "Fleet records link to remote targets without copying connection credentials.",
        ),
    )
