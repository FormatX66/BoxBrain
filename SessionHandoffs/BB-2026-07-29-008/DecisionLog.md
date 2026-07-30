# Decision Log

## BB-ADR-029

- **Date:** 2026-07-29
- **Decision:** Represent related keyboard work as one bounded
  `keyboard_sequence` operation executed inside one pinned RDP connection.
- **Reason:** Separate connections destroyed transient UI context and could not
  distinguish connection timing from key delivery.
- **Alternatives considered:**
  - Keep submitting one operation per RDP connection.
  - Expose a general long-lived RDP session token.
  - Add arbitrary FreeRDP command-line arguments.
- **Chosen solution:** Permit two to eight typed text/key steps with fixed
  per-step delays, total text/delay limits, exact identity checks, and one
  connection lifecycle.
- **Impact:** Transport evidence now covers a related input sequence without
  opening an unbounded session API.

## BB-ADR-030

- **Date:** 2026-07-29
- **Decision:** Treat Windows RDP session routing/unlock state as the active
  blocker and stop adding timing or shortcut variants.
- **Reason:** Three sequences reached transport success, including extended
  desktop-settle delays and both Win+R and Ctrl+Esc, while Notepad remained
  absent. Explorer stayed in session 1 and new attempts reached LogonUI
  processes in other sessions.
- **Alternatives considered:**
  - Increase delays again.
  - Add more key chords.
  - Claim UI success from FreeRDP transport success.
- **Chosen solution:** Inspect session ownership, Terminal Services events,
  reconnect behavior, and single-session policy before changing input code.
- **Impact:** The next work targets the evidenced layer and preserves truthful
  separation between transport acceptance and verified state change.

## BB-ADR-031

- **Date:** 2026-07-29
- **Decision:** Use a narrow UAC-gated checkpoint helper and grant the operator
  membership in the built-in Hyper-V Administrators group.
- **Reason:** The current medium-integrity token could not inspect or restore
  the VM, and automating or bypassing the UAC boundary was unacceptable.
- **Alternatives considered:**
  - Keep requiring ad hoc elevated commands.
  - Disable UAC or create a privileged background service.
  - Leave checkpoint recovery manual and undocumented.
- **Chosen solution:** Resolve one exact VM and checkpoint, support `-WhatIf`,
  require elevation, record success/failure receipts, and optionally add the
  current operator to the standard Hyper-V group.
- **Impact:** Checkpoint recovery is repeatable and auditable. A new Windows
  sign-in is required before the added membership reaches non-elevated tokens.
