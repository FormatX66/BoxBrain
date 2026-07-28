# BrainConnect Project Index

## Purpose

Provide an auditable controller that connects cloud AI planning to an isolated,
resettable computer lab through narrowly scoped plugins.

## Current status

Active alpha. The Flutter dashboard, authenticated FastAPI control plane,
durable SQLite task queue, append-only audit storage, policy profiles, and
persistent emergency stop are implemented. The dashboard now receives
authenticated, resumable live audit events with HTTP polling fallback. The
first observation protocol, target identity, allowlisting workflow, and
evidence-retention limits are specified. Durable target records, audited
enable/disable operations, enabled-target task admission, and the Flutter
target workflow are implemented. The observation-only transport is not yet
implemented. No keyboard, mouse, shell, remote-desktop, or model actions
execute.

## Metadata

- **Owner:** Bruce / BoxBrain operator
- **Priority:** P0
- **Completion:** 55% planning estimate
- **Current revision:** `dcc32b8` on `feature/brainconnect-target-registry`
- **Repository:** [Canonical local repository](../../../BrainConnect/README.md)
- **Remote repository:** [FormatX66/BrainConnect](https://github.com/FormatX66/BrainConnect)
- **Draft review:** [Pull request 2](https://github.com/FormatX66/BrainConnect/pull/2)

## Dependencies

- Flutter 3.44.8 and Dart 3.12.2
- Python 3.12, FastAPI, Uvicorn, Pydantic, SQLite, and pytest
- WebSocket Channel 3.0.3 for the cross-platform Flutter live-event client
- Future: FreeRDP 3.x for the out-of-process observation-only RDP plugin
- Future: AgentFramework planner contracts, Security controls, and Research
  benchmark definitions

## Documentation

- [Product requirements](../../../BrainConnect/docs/PRD.md)
- [Architecture](../../../BrainConnect/docs/ARCHITECTURE.md)
- [Roadmap](../../../BrainConnect/docs/ROADMAP.md)
- [Security](../../../BrainConnect/docs/SECURITY.md)
- [Development](../../../BrainConnect/docs/DEVELOPMENT.md)
- [Plugin contract](../../../BrainConnect/docs/PLUGIN_CONTRACT.md)
- [Observation targets](../../../BrainConnect/docs/TARGETS.md)

## Related projects

- [AgentFramework](../AgentFramework/ProjectIndex.md)
- [Automation](../Automation/ProjectIndex.md)
- [Security](../Security/ProjectIndex.md)
- [Research](../Research/ProjectIndex.md)

## Immediate next step

Implement an out-of-process, certificate-only FreeRDP probe that compares the
observed identity with the approved pin, rejects and disables mismatches, and
does not authenticate or expose remote input. The canonical task sequence is
tracked in the [Master TODO](../../Admin/MasterTODO.md).
