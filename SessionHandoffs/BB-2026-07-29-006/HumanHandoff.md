# Human Handoff

## What was accomplished

- Implemented BrainConnect's first native live-control artifact:
  `brainconnect-freerdp-control`.
- Limited the artifact to one absolute `pointer_move`; shell, keyboard,
  pointer buttons, scrolling, clipboard, and frames remain unavailable.
- Reused the pinned FreeRDP certificate callback and required exact endpoint,
  NLA/HYBRID selection, and SHA-256 certificate match before credential lookup.
- Selected systemd's runtime credential directory and bound credential names
  to the requested target UUID.
- Kept credential values out of Git, SQLite, API bodies, operation JSON,
  process arguments, ordinary environment variables, result objects, and audit
  events.
- Disabled clipboard, drive, device, audio, printer, smart-card, gateway,
  auto-reconnect, and file redirection.
- Added strict canonical request parsing, bounded result generation,
  owner-only credential-file checks, symlink rejection, hard deadline, desktop
  coordinate validation, and a bounded FreeRDP event-loop check.
- Proved on amd64 and arm64 that a wrong certificate fails before credential
  lookup and that a matched certificate with no credential sends no
  authentication data.
- Published BrainConnect commit `d207694` in draft pull request 10.

## Decisions made

- Use systemd `CREDENTIALS_DIRECTORY` with target-UUID-bound files, and read
  them only after the exact certificate matches.
- Make `pointer_move` the only first native capability. A successful result
  means FreeRDP accepted the event in the active pinned session; visual cursor
  confirmation remains a separate live evidence gate.

## Current blockers

- The control binary is not installed on the Pi.
- No target RDP credential is provisioned through systemd.
- The Pi's FreeRDP 3.26 runtime has not yet run the new control-specific
  fixtures.
- The existing guarded Pi installer promotes only the certificate probe.
- No before/after visual evidence proves cursor movement in the live Windows
  session.
- `executor_enabled` remains false and all operation kinds other than
  `pointer_move` remain unavailable at the native boundary.

## Immediate next step

Extend the existing guarded native installer without duplicating it, run the
control identity and credential-negative fixtures against the Pi's exact
runtime, provision encrypted target-bound systemd credentials, install the
artifact while execution remains disabled, and perform one evidence-backed
pointer move before restoring checkpoint `clean-linked-2026-07-29`.

## Long-term objective

Run repeatable, evidence-backed experiments against the exact disposable
Windows VM while expanding one typed capability at a time and constraining
only failures observed in the sandbox.
