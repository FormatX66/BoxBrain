# System Architecture

BoxBrain separates ecosystem knowledge from implementation source while making
both discoverable from one index.

```mermaid
flowchart TD
    BB["BoxBrain knowledge and coordination repository"]
    PI["Project and repository indexes"]
    GOV["Decisions, roadmap, changes, and handoffs"]
    BC["BrainConnect implementation repository"]
    AF["AgentFramework (proposed)"]
    SEC["Security (proposed)"]
    RES["Research (proposed)"]
    WEB["Website projects (discovery)"]

    BB --> PI
    BB --> GOV
    PI --> BC
    PI --> AF
    PI --> SEC
    PI --> RES
    PI --> WEB
    BC -. future shared contracts .-> AF
    BC -. cross-project controls .-> SEC
    BC -. benchmarks and evidence .-> RES
```

## Boundaries

- BoxBrain owns cross-project discovery, dependencies, priorities, decisions,
  and handoffs.
- Each registered repository owns its code, tests, and detailed technical
  documentation.
- A planned project receives only a project index until source or requirements
  are discovered.
- Links replace copied documents.

## Current dependency path

The active execution path is BoxBrain governance → BrainConnect repository →
Flutter UI and FastAPI controller → future observation-only target plugin.

See [BrainConnect’s canonical architecture](../../BrainConnect/docs/ARCHITECTURE.md)
for component-level details and [Integrations](Integrations.md) for registered
boundaries.
