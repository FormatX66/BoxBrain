# Agent Handoff — BB-2026-07-28-002

## Current objective

Add durable observation-target identity and allowlisting before implementing
any RDP or VNC transport.

## Tasks

1. Confirm both repositories begin clean.
2. Create `feature/brainconnect-target-registry`.
3. Define target identity, endpoint, transport, enabled state, and evidence
   retention metadata.
4. Add authenticated target registration and listing APIs.
5. Require an allowlisted target ID when a task is created.
6. Add migration, restart-persistence, authorization, and rejection tests.
7. Update the Flutter target view without adding input controls.
8. Update BrainConnect docs and generate the next BoxBrain handoff.

## Dependencies

- BrainConnect revision `9515d02`
- Existing bearer authentication, SQLite migrations, audit events, emergency
  stop, and live-event stream
- A decision between RDP and VNC for the first observer
- Defined target retention and redaction policy

## Files affected

- BrainConnect controller API, models, database, event stream, Flutter service,
  dashboard lifecycle, dependency lock, tests, and documentation
- BoxBrain BrainConnect index, roadmap, TODO, decisions, changes, integrations,
  validator, and session records

Detailed changes are in the [session change log](ChangeLog.md).

## Required repositories

- This BoxBrain repository
- [BrainConnect canonical repository](https://github.com/FormatX66/BrainConnect)

## Verification checklist

- Run BrainConnect backend, Flutter analysis, Flutter tests, and web build.
- Verify unlisted targets cannot be queued or observed.
- Verify runtime secrets, databases, captures, and build output remain ignored.
- Run the BoxBrain repository validator.

## Suggested commit message

`feat: add allowlisted observation targets`

## Suggested branch

`feature/brainconnect-target-registry`

## Potential risks

- The local Flutter web build embeds a development bearer token and must not be
  published.
- Fixed two-second reconnects could create noisy retries during long outages;
  bounded exponential backoff is a future improvement.
- The dashboard audit list is not yet capped for long-running sessions.
- Native WebSocket clients do not send browser origins, so token authentication
  remains their primary stream boundary.
- Starlette’s current TestClient emits an upstream `httpx2` migration warning.

## Estimated completion order

1. Target identity schema and decision
2. SQLite target registry and audit events
3. Authenticated target APIs and task enforcement
4. Flutter read-only target status
5. Tests and BoxBrain handoff
6. Observation-only RDP or VNC plugin
