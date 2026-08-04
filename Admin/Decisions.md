# Decision Index

Architectural decisions are recorded once in the session where they were made.
This file is the permanent searchable index.

| ID | Date | Decision | Canonical record |
| --- | --- | --- | --- |
| BB-ADR-054 | 2026-08-03 | Expose USB keyboard and mouse as separate HID functions and keep Bluetooth HID behind its own explicit pairing boundary. | [Session decision log](../SessionHandoffs/BB-2026-08-03-001/DecisionLog.md#bb-adr-054) |
| BB-ADR-053 | 2026-08-03 | Treat the Raspberry Pi 4 as the canonical BoxBrain core appliance and transport owner. | [Session decision log](../SessionHandoffs/BB-2026-08-03-001/DecisionLog.md#bb-adr-053) |
| BB-ADR-050 | 2026-07-31 | Use rclone's shared Google OAuth client only for the initial proof and migrate to a dedicated BoxBrain client before retirement. | [Session decision log](../SessionHandoffs/BB-2026-07-31-001/DecisionLog.md#bb-adr-050) |
| BB-ADR-047 | 2026-07-31 | Use `boxbrainprime@gmail.com` with one BoxBrain Drive root and device-partitioned operational paths. | [Session decision log](../SessionHandoffs/BB-2026-07-31-001/DecisionLog.md#bb-adr-047) |
| BB-ADR-048 | 2026-07-31 | Adopt root-folder-scoped rclone with private writable token state and non-deleting copies for Pi Drive transport. | [Session decision log](../SessionHandoffs/BB-2026-07-31-001/DecisionLog.md#bb-adr-048) |
| BB-ADR-049 | 2026-07-31 | Automatically verify Drive patches but require explicit pinned-SFTP delivery and perform no execution. | [Session decision log](../SessionHandoffs/BB-2026-07-31-001/DecisionLog.md#bb-adr-049) |
| BB-ADR-044 | 2026-07-30 | Normalize remote shell installers to LF at deployment time and enforce LF through Git attributes. | [Session decision log](../SessionHandoffs/BB-2026-07-30-002/DecisionLog.md#bb-adr-044) |
| BB-ADR-045 | 2026-07-30 | Accept scrolling only when identical bounded frame regions produce different controller-verified hashes after the exact wheel action. | [Session decision log](../SessionHandoffs/BB-2026-07-30-002/DecisionLog.md#bb-adr-045) |
| BB-ADR-046 | 2026-07-30 | Permit exact named-checkpoint restoration by members of the local Hyper-V Administrators group without requiring a fully elevated shell. | [Session decision log](../SessionHandoffs/BB-2026-07-30-002/DecisionLog.md#bb-adr-046) |
| BB-ADR-042 | 2026-07-30 | Use authoritative GitHub `main` URLs for cross-repository documentation instead of sibling-checkout paths. | [Session decision log](../SessionHandoffs/BB-2026-07-30-001/DecisionLog.md#bb-adr-042) |
| BB-ADR-043 | 2026-07-30 | Integrate a validated stacked PR series bottom-up with merge commits and exact-head-SHA guards. | [Session decision log](../SessionHandoffs/BB-2026-07-30-001/DecisionLog.md#bb-adr-043) |
| BB-ADR-051 | 2026-07-31 | Separate automatic SSID discovery from explicitly authorized, transient saved-key retrieval. | [Session decision log](../SessionHandoffs/BB-2026-07-31-001/DecisionLog.md#bb-adr-051) |
| BB-ADR-052 | 2026-07-31 | Use a fixed, hash-verified and SSH-verified USB-HID bootstrap for compatible headless Windows consoles. | [Session decision log](../SessionHandoffs/BB-2026-07-31-001/DecisionLog.md#bb-adr-052) |
| BB-ADR-041 | 2026-07-29 | Select scrolling before shell or clipboard and bind every scroll to absolute coordinates plus at most ten standard wheel steps. | [Session decision log](../SessionHandoffs/BB-2026-07-29-012/DecisionLog.md#bb-adr-041) |
| BB-ADR-039 | 2026-07-29 | Require both persisted execution configuration and authenticated live health to prove an inert controller before upgrade. | [Session decision log](../SessionHandoffs/BB-2026-07-29-011/DecisionLog.md#bb-adr-039) |
| BB-ADR-040 | 2026-07-29 | Separate low-impact daytime work from Pi, VM, Flutter, and cross-architecture nightshift verification. | [Session decision log](../SessionHandoffs/BB-2026-07-29-011/DecisionLog.md#bb-adr-040) |
| BB-ADR-001 | 2026-07-28 | Use BoxBrain as a knowledge/control repository and keep implementation repositories authoritative. | [Session decision log](../SessionHandoffs/BB-2026-07-28-001/DecisionLog.md#bb-adr-001) |
| BB-ADR-002 | 2026-07-28 | Make session records canonical and cumulative admin logs indexes. | [Session decision log](../SessionHandoffs/BB-2026-07-28-001/DecisionLog.md#bb-adr-002) |
| BB-ADR-003 | 2026-07-28 | Represent undiscovered projects with metadata-only placeholders. | [Session decision log](../SessionHandoffs/BB-2026-07-28-001/DecisionLog.md#bb-adr-003) |
| BB-ADR-004 | 2026-07-28 | Use an authenticated WebSocket for browser-compatible live audit events. | [Session decision log](../SessionHandoffs/BB-2026-07-28-002/DecisionLog.md#bb-adr-004) |
| BB-ADR-005 | 2026-07-28 | Retain cursor-based HTTP polling as a deduplicating fallback. | [Session decision log](../SessionHandoffs/BB-2026-07-28-002/DecisionLog.md#bb-adr-005) |
| BB-ADR-006 | 2026-07-28 | Use an observation-only FreeRDP plugin with pinned certificate identity and disabled-by-default target approval. | [Session decision log](../SessionHandoffs/BB-2026-07-28-003/DecisionLog.md#bb-adr-006) |
| BB-ADR-007 | 2026-07-28 | Consolidate the canonical organization into the existing BoxBrain remote through a review branch. | [Session decision log](../SessionHandoffs/BB-2026-07-28-003/DecisionLog.md#bb-adr-007) |
| BB-ADR-008 | 2026-07-28 | Persist target identity separately from authority and admit tasks only for explicitly enabled target UUIDs. | [Session decision log](../SessionHandoffs/BB-2026-07-28-004/DecisionLog.md#bb-adr-008) |
| BB-ADR-009 | 2026-07-28 | Isolate certificate observation behind a versioned, fail-closed helper protocol and permit pre-approval probes of registered targets. | [Session decision log](../SessionHandoffs/BB-2026-07-28-005/DecisionLog.md#bb-adr-009) |
| BB-ADR-010 | 2026-07-28 | Pin the native certificate helper to FreeRDP 3.15.x and emit observations only after exact NLA/HYBRID server selection. | [Session decision log](../SessionHandoffs/BB-2026-07-28-006/DecisionLog.md#bb-adr-010) |
| BB-ADR-011 | 2026-07-28 | Deploy the reviewed arm64 helper to the Pi only after an exact runtime check and on-host boundary test, with content-addressed provenance. | [Session decision log](../SessionHandoffs/BB-2026-07-28-007/DecisionLog.md#bb-adr-011) |
| BB-ADR-012 | 2026-07-28 | Run the Pi controller as an immutable, USB-bound, unprivileged systemd service promoted only after authenticated foreground verification. | [Session decision log](../SessionHandoffs/BB-2026-07-28-008/DecisionLog.md#bb-adr-012) |
| BB-ADR-013 | 2026-07-29 | Verify the RDP certificate boundary with an ephemeral Pi-loopback NLA fixture and keep full desktop testing separate. | [Session decision log](../SessionHandoffs/BB-2026-07-29-001/DecisionLog.md#bb-adr-013) |
| BB-ADR-014 | 2026-07-29 | Preserve only `HOME` in the controller's minimal native-helper environment because FreeRDP requires it to create a context. | [Session decision log](../SessionHandoffs/BB-2026-07-29-001/DecisionLog.md#bb-adr-014) |
| BB-ADR-015 | 2026-07-29 | Stop and disable an earlier Pi controller revision before foreground upgrade verification, then re-enable only after the gate passes. | [Session decision log](../SessionHandoffs/BB-2026-07-29-001/DecisionLog.md#bb-adr-015) |
| BB-ADR-016 | 2026-07-29 | Use a Pi-only Generation 2 Hyper-V VM as the disposable full Windows target and apply verified media directly to its blank VHD when needed. | [Session decision log](../SessionHandoffs/BB-2026-07-29-002/DecisionLog.md#bb-adr-016) |
| BB-ADR-017 | 2026-07-29 | Separate future RDP observation from a restricted, non-administrator, Pi-only SSH diagnostic account. | [Session decision log](../SessionHandoffs/BB-2026-07-29-002/DecisionLog.md#bb-adr-017) |
| BB-ADR-018 | 2026-07-29 | Give Windows device inventory its own 15-second deadline and report incomplete coverage explicitly. | [Session decision log](../SessionHandoffs/BB-2026-07-29-002/DecisionLog.md#bb-adr-018) |
| BB-ADR-019 | 2026-07-29 | Read the Windows RDP certificate through Hyper-V PowerShell Direct before comparing it with BrainConnect's no-authentication probe. | [Session decision log](../SessionHandoffs/BB-2026-07-29-003/DecisionLog.md#bb-adr-019) |
| BB-ADR-020 | 2026-07-29 | Revoke and rotate any controller token exposed in diagnostic output before continuing operations. | [Session decision log](../SessionHandoffs/BB-2026-07-29-003/DecisionLog.md#bb-adr-020) |
| BB-ADR-021 | 2026-07-29 | Start disposable-VM control capability-first, while retaining exact-target containment, audit, emergency stop, hard limits, and checkpoint recovery. | [Session decision log](../SessionHandoffs/BB-2026-07-29-004/DecisionLog.md#bb-adr-021) |
| BB-ADR-022 | 2026-07-29 | Separate durable execution state from live VM transport through a fixed, disabled-by-default standard-input adapter protocol with transient output. | [Session decision log](../SessionHandoffs/BB-2026-07-29-005/DecisionLog.md#bb-adr-022) |
| BB-ADR-023 | 2026-07-29 | Supply RDP credentials through target-UUID-bound systemd runtime files read only after exact endpoint and certificate verification. | [Session decision log](../SessionHandoffs/BB-2026-07-29-006/DecisionLog.md#bb-adr-023) |
| BB-ADR-024 | 2026-07-29 | Make absolute `pointer_move` the first native capability and distinguish accepted input from visually verified state change. | [Session decision log](../SessionHandoffs/BB-2026-07-29-006/DecisionLog.md#bb-adr-024) |
| BB-ADR-025 | 2026-07-29 | Accept systemd root-owned `0440` runtime credentials only with a named service-account read ACL and all other safety checks. | [Session decision log](../SessionHandoffs/BB-2026-07-29-007/DecisionLog.md#bb-adr-025) |
| BB-ADR-026 | 2026-07-29 | Keep exact-session event submission separate from independently verified target-state change. | [Session decision log](../SessionHandoffs/BB-2026-07-29-007/DecisionLog.md#bb-adr-026) |
| BB-ADR-027 | 2026-07-29 | Retain the content-addressed input binary inert while removing the execution drop-in and all encrypted credentials after each run. | [Session decision log](../SessionHandoffs/BB-2026-07-29-007/DecisionLog.md#bb-adr-027) |
| BB-ADR-028 | 2026-07-29 | Add only the verified left Windows key to the fixed key allowlist. | [Session decision log](../SessionHandoffs/BB-2026-07-29-007/DecisionLog.md#bb-adr-028) |
| BB-ADR-029 | 2026-07-29 | Execute related keyboard steps as one bounded operation in one pinned RDP connection. | [Session decision log](../SessionHandoffs/BB-2026-07-29-008/DecisionLog.md#bb-adr-029) |
| BB-ADR-030 | 2026-07-29 | Treat Windows session routing and unlock state as the active input blocker. | [Session decision log](../SessionHandoffs/BB-2026-07-29-008/DecisionLog.md#bb-adr-030) |
| BB-ADR-031 | 2026-07-29 | Use a UAC-gated exact-checkpoint helper and standard Hyper-V group membership. | [Session decision log](../SessionHandoffs/BB-2026-07-29-008/DecisionLog.md#bb-adr-031) |
| BB-ADR-032 | 2026-07-29 | Bind the local Windows credential and console session, force slow-path input, and reject suspended input. | [Session decision log](../SessionHandoffs/BB-2026-07-29-009/DecisionLog.md#bb-adr-032) |
| BB-ADR-033 | 2026-07-29 | Accept an optional UTF-8 byte-order marker only at the local Windows experiment-plan boundary. | [Session decision log](../SessionHandoffs/BB-2026-07-29-009/DecisionLog.md#bb-adr-033) |
| BB-ADR-034 | 2026-07-29 | Limit live frame observation to one bounded memory-only region with validated cursor, format, and pixel hash. | [Session decision log](../SessionHandoffs/BB-2026-07-29-010/DecisionLog.md#bb-adr-034) |
| BB-ADR-035 | 2026-07-29 | Establish the standard target-user RDP session and wait ten seconds for desktop readiness. | [Session decision log](../SessionHandoffs/BB-2026-07-29-010/DecisionLog.md#bb-adr-035) |
| BB-ADR-036 | 2026-07-29 | Reserve native standard output for canonical JSON and route FreeRDP diagnostics to standard error. | [Session decision log](../SessionHandoffs/BB-2026-07-29-010/DecisionLog.md#bb-adr-036) |
| BB-ADR-037 | 2026-07-29 | Require absolute coordinates and atomic move-plus-button delivery for every pointer-button request. | [Session decision log](../SessionHandoffs/BB-2026-07-29-010/DecisionLog.md#bb-adr-037) |
| BB-ADR-038 | 2026-07-29 | Rotate an exposed lab credential, retire checkpoints with its old state, and create a new verified checkpoint. | [Session decision log](../SessionHandoffs/BB-2026-07-29-010/DecisionLog.md#bb-adr-038) |

Before adding a decision, search this index and the linked session logs.
