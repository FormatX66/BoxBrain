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
`clean-linked-rotated-2026-07-29`. The earlier
`clean-linked-2026-07-29` checkpoint is retired after the lab credential was
rotated. Its RDP identity was independently read from the
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
pointer movement, coordinate-bound button events, bounded Unicode text, fixed
allowlisted key or chord input, a two-to-eight-step keyboard sequence inside
one pinned connection, and bounded memory-only frame regions. It
rechecks the exact endpoint, selected NLA/HYBRID protocol, and SHA-256
certificate pin before reading target-bound systemd runtime credentials,
disables all FreeRDP redirections, validates coordinates and keyboard payloads,
and disconnects after a bounded event loop. The connector and credential
contract pass seven native tests for amd64 and arm64. Revision `567ffa3` is
installed on the Pi with control SHA-256
`090929ac598855b5da72732a08975a291fa84d4cfbb718585665c8c747c5077e`.
It binds the target-local account, establishes the standard target-user
session, waits ten seconds for desktop readiness, forces slow-path input, and
rejects suspended input. Independent process checks proved Task Manager and
Notepad launch. Frame evidence proved visible text and an absolute click by
showing `|CLICK|` inserted at the clicked Notepad caret position. Cleanup left
`executor_enabled=false`, removed the execution drop-in, every encrypted
credential, and every temporary runner, and restored the rotated clean
checkpoint.

Controller revision `be0738c` adds a read-only upgrade preflight before local
wheel construction or remote upload. It rejects an enabled execution drop-in
and requires an active controller to report authenticated
`executor_enabled=false`, production health, and an armed emergency stop.
Revision `494ec3f` adds source-complete pointer scrolling. Each scroll moves to
explicit absolute coordinates and then emits no more than ten standard
120-unit vertical or horizontal wheel steps in the same pinned RDP connection.
The controller limits and dashboard form passed focused local checks; native
cross-build, Pi promotion, and independent live frame proof remain queued for
nightshift.

## Metadata

- **Owner:** Bruce / BoxBrain operator
- **Priority:** P0
- **Completion:** 98% planning estimate
- **Current revision:** `494ec3f` on
  `feature/brainconnect-rdp-input-verification`
- **Repository:** [Canonical GitHub repository](https://github.com/FormatX66/BrainConnect)
- **Remote repository:** [FormatX66/BrainConnect](https://github.com/FormatX66/BrainConnect)
- **Draft review:** [Pull request 12](https://github.com/FormatX66/BrainConnect/pull/12)

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
  `clean-linked-rotated-2026-07-29`
- Future: AgentFramework planner contracts, Security controls, and Research
  benchmark definitions

## Documentation

- [Product requirements](https://github.com/FormatX66/BrainConnect/blob/main/docs/PRD.md)
- [Architecture](https://github.com/FormatX66/BrainConnect/blob/main/docs/ARCHITECTURE.md)
- [Roadmap](https://github.com/FormatX66/BrainConnect/blob/main/docs/ROADMAP.md)
- [Security](https://github.com/FormatX66/BrainConnect/blob/main/docs/SECURITY.md)
- [Open-lab control](https://github.com/FormatX66/BrainConnect/blob/main/docs/OPEN_LAB.md)
- [Open-lab adapter protocol](https://github.com/FormatX66/BrainConnect/blob/main/plugins/open-lab-control/PROTOCOL.md)
- [Deterministic adapter fixture](https://github.com/FormatX66/BrainConnect/blob/main/lab/open-lab-fixture/README.md)
- [Development](https://github.com/FormatX66/BrainConnect/blob/main/docs/DEVELOPMENT.md)
- [Plugin contract](https://github.com/FormatX66/BrainConnect/blob/main/docs/PLUGIN_CONTRACT.md)
- [Observation targets](https://github.com/FormatX66/BrainConnect/blob/main/docs/TARGETS.md)
- [RDP helper protocol](https://github.com/FormatX66/BrainConnect/blob/main/plugins/rdp-observer/PROTOCOL.md)
- [Native helper build](https://github.com/FormatX66/BrainConnect/blob/main/plugins/rdp-observer/native/README.md)
- [Raspberry Pi controller deployment](https://github.com/FormatX66/BrainConnect/blob/main/installer/pi/README.md)
- [Raspberry Pi RDP identity live lab](https://github.com/FormatX66/BrainConnect/blob/main/lab/pi-rdp-fixture/README.md)
- [Hyper-V Windows target runbook](../../sandbox/hyperv/README.md)

## Related projects

- [AgentFramework](../AgentFramework/ProjectIndex.md)
- [Automation](../Automation/ProjectIndex.md)
- [Security](../Security/ProjectIndex.md)
- [Research](../Research/ProjectIndex.md)

## Immediate next step

Run the documented nightshift gates for scrolling: full controller and Flutter
verification, warnings-as-errors amd64/arm64 builds, real-Pi upgrade preflight,
exact FreeRDP 3.26 compatibility, artifact promotion, and one bounded
before/after frame proof against the rotated checkpoint. The canonical task
sequence is tracked in the
[Master TODO](../../Admin/MasterTODO.md).
