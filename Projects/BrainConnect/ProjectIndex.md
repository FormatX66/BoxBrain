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
target workflow are implemented. The fail-closed certificate-probe API,
versioned helper protocol, verification audit events, atomic mismatch
disablement, and Flutter probe control are implemented. The native FreeRDP
3.15.x certificate helper now builds and passes synthetic RDP/TLS, downgrade,
deadline, protocol, and no-authentication tests for amd64 and arm64. Linux/Pi
installation is now complete on the Kali Raspberry Pi 4 with exact runtime,
checksum, ownership, provenance, and on-host synthetic verification. The
authenticated controller is deployed there as an immutable, USB-bound,
unprivileged systemd service with private token and SQLite state. An isolated
Windows live test and frame transport remain. No keyboard, mouse, shell,
remote-desktop, or model actions execute.

## Metadata

- **Owner:** Bruce / BoxBrain operator
- **Priority:** P0
- **Completion:** 78% planning estimate
- **Current revision:** `ee9c518` on `feature/brainconnect-pi4-controller`
- **Repository:** [Canonical local repository](../../../BrainConnect/README.md)
- **Remote repository:** [FormatX66/BrainConnect](https://github.com/FormatX66/BrainConnect)
- **Draft review:** [Pull request 6](https://github.com/FormatX66/BrainConnect/pull/6)

## Dependencies

- Flutter 3.44.8 and Dart 3.12.2
- Python 3.12, FastAPI, Uvicorn, Pydantic, SQLite, and pytest
- WebSocket Channel 3.0.3 for the cross-platform Flutter live-event client
- Debian 13 build image pinned by digest, FreeRDP 3.15.x, CMake, GCC, and
  OpenSSL 3
- Kali 2026.2 Raspberry Pi 4 with `libfreerdp3-3` `3.26.0+dfsg-1`
- Deployed: Kali Raspberry Pi 4 controller service on direct USB
  `10.12.194.1:8000`
- Future: isolated disposable Windows RDP target
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
- [RDP helper protocol](../../../BrainConnect/plugins/rdp-observer/PROTOCOL.md)
- [Native helper build](../../../BrainConnect/plugins/rdp-observer/native/README.md)
- [Raspberry Pi controller deployment](../../../BrainConnect/installer/pi/README.md)

## Related projects

- [AgentFramework](../AgentFramework/ProjectIndex.md)
- [Automation](../Automation/ProjectIndex.md)
- [Security](../Security/ProjectIndex.md)
- [Research](../Research/ProjectIndex.md)

## Immediate next step

Select the isolated disposable Windows RDP target and verify exact-match,
changed-certificate, timeout, unreachable, and pre-authentication abort
behavior without enabling desktop sessions or input. The canonical task
sequence is tracked in the [Master TODO](../../Admin/MasterTODO.md).
