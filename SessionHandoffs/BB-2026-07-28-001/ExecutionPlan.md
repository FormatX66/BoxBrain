# Execution Plan — BB-2026-07-28-001

## Phase 1 — Repository foundation (complete)

1. BoxBrain required files, local links, and orphan checks passed.
2. BrainConnect Git state and automated checks passed.
3. The verification checklist was updated with evidence.
4. BoxBrain was initialized and captured in local Git.

## Phase 2 — BrainConnect live events

1. Create `feature/brainconnect-live-events`.
2. Add an authenticated event-stream endpoint backed by the audit sequence.
3. Add reconnect, cursor resume, and keepalive behavior.
4. Connect the Flutter dashboard with authorization headers.
5. Keep polling as a temporary fallback.
6. Add backend and UI tests.
7. Update the BrainConnect and BoxBrain project records.

## Phase 3 — Observation-only target

1. Define target identity and allowlisting.
2. Specify retention, sampling, and redaction.
3. Implement one out-of-process RDP or VNC observer.
4. Prove observation and audit without input execution.

## Stop conditions

- Do not add keyboard, mouse, shell, or self-modification execution in Phase 2
  or Phase 3.
- Do not create new project repositories without confirmed scope and owner.
- Do not move BrainConnect until repository remotes and migration intent are
  explicitly confirmed.
