# Execution Plan — BB-2026-07-28-002

## Phase 1 — Target identity decision

1. Choose the first observation protocol: RDP or VNC.
2. Define stable target ID, display name, endpoint, transport, enabled state,
   and identity-verification evidence.
3. Define who can change allowlist state and how changes are audited.
4. Define screenshot and observation retention limits.

## Phase 2 — Durable target registry

1. Add a versioned SQLite migration for targets.
2. Add authenticated list, create, update-state, and read endpoints.
3. Audit every target registration and state change.
4. Require an enabled, allowlisted target when creating a task.
5. Preserve emergency-stop transaction behavior.

## Phase 3 — Read-only UI and verification

1. Add a read-only target status view in Flutter.
2. Receive target registry changes through the existing live stream.
3. Test restart persistence, invalid identities, unlisted targets, disabled
   targets, authentication, audit ordering, and polling fallback.
4. Update BrainConnect and BoxBrain documentation.

## Phase 4 — Observation-only adapter

1. Implement one out-of-process observer for the selected protocol.
2. Capture bounded frames with redaction and retention.
3. Verify that no keyboard, mouse, clipboard, file, or shell capability exists.

## Stop conditions

- Do not add input execution during the target registry or observer milestone.
- Do not accept a target using network reachability alone; verify its declared
  identity.
- Do not persist target credentials or captures in Git.
