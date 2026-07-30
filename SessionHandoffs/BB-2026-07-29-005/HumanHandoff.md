# Human Handoff

## What was accomplished

- Added the disabled-by-default BrainConnect execution layer behind the
  open-lab operation queue.
- Defined a fixed version 1 process protocol for shell, keyboard, pointer, and
  clipboard operations.
- Kept target and operation data out of process arguments by sending bounded
  JSON through standard input.
- Reused the no-authentication RDP certificate probe before every execution
  claim.
- Added an atomic recheck of emergency stop, queued operation, active open
  task, and enabled target immediately before recording `running`.
- Added durable success/failure state, timestamps, failure categories,
  duration, output size/digest, and restart recovery to
  `failed/interrupted`.
- Kept raw output transient: it returns only to the authenticated caller and is
  not stored or copied into audit events.
- Added a packaged deterministic subprocess fixture covering all eight
  operation kinds and the declared failure categories. The full controller API
  to subprocess round trip passes without touching the VM.
- Added Flutter status chips, truthful executor visibility, gated **Run next**,
  and transient result display.
- Published BrainConnect revision `310c264` to draft pull request 9.

## Decisions made

- Separate durable controller execution state from the transport-specific live
  connector.
- Use one fixed executable with a version-only argument list and bounded JSON
  over standard input.
- Treat adapter output as transient content while persisting only size and
  SHA-256 digest.
- Keep the feature disabled unless an administrator supplies both an enabled
  switch and an absolute reviewed executable.

## Current blockers

- No live VM connector is implemented or installed.
- The adapter still needs an external credential provider that never exposes a
  password or token through Git, SQLite, API bodies, process arguments, logs,
  or audit events.
- Keyboard/pointer desktop-session correlation and modifier cleanup are not
  proven against the live Windows VM.
- Shell and clipboard transport choices are not finalized.
- Before/after evidence and clean-checkpoint restoration are still pending for
  the first live action.

## Immediate next step

Build the live FreeRDP-based connector behind the proven protocol, beginning
with credential and desktop-session correlation plus one low-impact pointer or
keyboard operation. Keep the Pi deployment disabled until the connector passes
fixture, identity, timeout, interruption, and live checkpoint gates.

## Long-term objective

Run repeatable, evidence-backed control experiments on the disposable Windows
VM and tighten only the capabilities or parameters that produce observed
failures.
