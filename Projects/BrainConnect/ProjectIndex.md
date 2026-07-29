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
unprivileged systemd service with private token and SQLite state. A live
Pi-loopback RDP/NLA fixture has verified exact identity matching, certificate
rotation and atomic disablement, unreachable and timeout handling, and
pre-authentication rejection. A disposable Windows 11 Enterprise Hyper-V
target now exists at `10.12.194.9:3389` on the Pi USB network, has a restricted
Pi-only diagnostic link, and is preserved at clean Standard checkpoint
`clean-linked-2026-07-29`. Its RDP identity was independently read from the
guest certificate store, registered disabled by default, exactly matched by
the Pi helper without authentication or a desktop session, audited, and then
enabled. BrainConnect now accepts bounded shell, keyboard, pointer, and
clipboard operations into an audited open-profile queue. Each operation is
tied to the active task and enabled target, and rechecks emergency stop and the
500-operation task limit. The Flutter dashboard provides forms for all eight
operation types and displays queued operation counts. The open-lab control
plugin now has a fixed, versioned standard-input protocol, exact certificate
recheck, atomic execution claims, durable results, interruption recovery, and
a packaged deterministic fixture. Flutter shows operation states, gates
**Run next** on truthful executor health, and displays raw result text only
transiently. A native FreeRDP connector now implements canonical absolute
pointer movement, bounded Unicode text, and fixed allowlisted key or chord
input. It rechecks the exact endpoint, selected NLA/HYBRID protocol, and
SHA-256 certificate pin before reading target-bound systemd runtime
credentials, disables all FreeRDP redirections, validates coordinates and
keyboard payloads, and disconnects after a bounded event loop. The connector
and credential contract pass native amd64 and arm64 builds and tests. Revision
`fd2281e` is installed on the Pi with control SHA-256
`1d91cf630e7b1f16f8c95bc871479218caa86a1e9d7d9aa8aa3aebdbaa59b74b`.
A guarded live run proved exact-target authentication and successful FreeRDP
event submission for pointer, text, and key operations. Independent guest
process checks did not prove a durable UI-state change. Cleanup left
`executor_enabled=false`, removed the execution drop-in, and deleted every
encrypted target credential.

## Metadata

- **Owner:** Bruce / BoxBrain operator
- **Priority:** P0
- **Completion:** 95% planning estimate
- **Current revision:** `e81f5f5` on `feature/brainconnect-freerdp-input`
- **Repository:** [Canonical local repository](../../../BrainConnect/README.md)
- **Remote repository:** [FormatX66/BrainConnect](https://github.com/FormatX66/BrainConnect)
- **Draft review:** [Pull request 11](https://github.com/FormatX66/BrainConnect/pull/11)

## Dependencies

- Flutter 3.44.8 and Dart 3.12.2
- Python 3.12, FastAPI, Uvicorn, Pydantic, SQLite, and pytest
- WebSocket Channel 3.0.3 for the cross-platform Flutter live-event client
- Debian 13 build image pinned by digest, FreeRDP 3.15.x, CMake, GCC, and
  OpenSSL 3
- Kali 2026.2 Raspberry Pi 4 with `libfreerdp3-3` `3.26.0+dfsg-1`
- Target-UUID-bound systemd runtime credentials, provisioned only at deployment
  and never stored in Git, SQLite, API payloads, command arguments, or ordinary
  environment values
- Deployed: Kali Raspberry Pi 4 controller service on direct USB
  `10.12.194.1:8000`
- Live-approved: isolated Windows 11 Enterprise Evaluation 25H2 Hyper-V target
  at `10.12.194.9:3389`, based on checkpoint
  `clean-linked-2026-07-29`
- Future: AgentFramework planner contracts, Security controls, and Research
  benchmark definitions

## Documentation

- [Product requirements](../../../BrainConnect/docs/PRD.md)
- [Architecture](../../../BrainConnect/docs/ARCHITECTURE.md)
- [Roadmap](../../../BrainConnect/docs/ROADMAP.md)
- [Security](../../../BrainConnect/docs/SECURITY.md)
- [Open-lab control](../../../BrainConnect/docs/OPEN_LAB.md)
- [Open-lab adapter protocol](../../../BrainConnect/plugins/open-lab-control/PROTOCOL.md)
- [Deterministic adapter fixture](../../../BrainConnect/lab/open-lab-fixture/README.md)
- [Development](../../../BrainConnect/docs/DEVELOPMENT.md)
- [Plugin contract](../../../BrainConnect/docs/PLUGIN_CONTRACT.md)
- [Observation targets](../../../BrainConnect/docs/TARGETS.md)
- [RDP helper protocol](../../../BrainConnect/plugins/rdp-observer/PROTOCOL.md)
- [Native helper build](../../../BrainConnect/plugins/rdp-observer/native/README.md)
- [Raspberry Pi controller deployment](../../../BrainConnect/installer/pi/README.md)
- [Raspberry Pi RDP identity live lab](../../../BrainConnect/lab/pi-rdp-fixture/README.md)
- [Hyper-V Windows target runbook](../../sandbox/hyperv/README.md)

## Related projects

- [AgentFramework](../AgentFramework/ProjectIndex.md)
- [Automation](../Automation/ProjectIndex.md)
- [Security](../Security/ProjectIndex.md)
- [Research](../Research/ProjectIndex.md)

## Immediate next step

Restore checkpoint `clean-linked-2026-07-29` with an authorized Hyper-V
account, re-probe the target certificate, and implement one bounded persistent
RDP input sequence with independent frame or guest-state verification. Repeat
a harmless key or pointer experiment while recording transport acceptance
separately from verified state change. Disable the executor and remove all
encrypted target credentials after the run. Shell, pointer buttons, scrolling,
clipboard, and observation-only frames remain pending tracks. The canonical
task sequence is tracked in the
[Master TODO](../../Admin/MasterTODO.md).
