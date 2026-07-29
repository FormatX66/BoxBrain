# Decision Index

Architectural decisions are recorded once in the session where they were made.
This file is the permanent searchable index.

| ID | Date | Decision | Canonical record |
| --- | --- | --- | --- |
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

Before adding a decision, search this index and the linked session logs.
