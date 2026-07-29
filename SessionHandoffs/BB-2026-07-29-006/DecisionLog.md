# Decision Log

## BB-ADR-023

- **Date:** 2026-07-29
- **Decision:** Supply native RDP credentials through systemd's runtime
  credential directory, use target-UUID-bound credential names, and read them
  only after exact endpoint and certificate verification.
- **Reason:** The adapter needs authentication material without moving it
  through the controller database, operation payload, process arguments,
  result protocol, logs, or audit stream. Target-specific names prevent one
  enabled request from silently selecting another target's account.
- **Alternatives considered:**
  - Command-line username and password values.
  - Ordinary environment variables.
  - SQLite or controller-managed secret storage.
  - A new root-owned Unix credential socket.
  - An external cloud secrets service.
- **Chosen solution:** Inherit only systemd's non-secret
  `CREDENTIALS_DIRECTORY` path. After the pinned certificate matches, read
  owner-only `rdp-<target-uuid>-username`, `-password`, and optional `-domain`
  files with no-follow, regular-file, single-link, ownership, permission, size,
  and control-character checks.
- **Impact:** The first connector has a concrete runtime credential contract
  without adding secret persistence or another service. Pi promotion must
  provision and roll back encrypted systemd credentials separately.

## BB-ADR-024

- **Date:** 2026-07-29
- **Decision:** Make one absolute FreeRDP `pointer_move` the only first native
  execution capability and define success as event acceptance in the active
  pinned session, not visual state confirmation.
- **Reason:** Pointer movement has minimal target-state impact and avoids text,
  clipboard, file, or shell disclosure. FreeRDP can prove session activation
  and event acceptance before BrainConnect has an observation-frame verifier.
- **Alternatives considered:**
  - Implement every queued operation kind in one connector.
  - Start with keyboard text or a key chord.
  - Start with clipboard read.
  - Report visual success without an independent observation.
- **Chosen solution:** Reject every operation except canonical
  `pointer_move`, validate coordinates against negotiated dimensions, send one
  event, keep the session active through a bounded event-loop check, and
  disconnect with all redirections disabled.
- **Impact:** The artifact can be runtime-tested without broad capability
  expansion. A live promotion still requires independent before/after cursor
  evidence before claiming visual movement.
