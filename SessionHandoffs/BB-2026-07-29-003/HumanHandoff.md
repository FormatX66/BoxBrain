# Human Handoff

## What was accomplished

- Confirmed RDP reachable at `10.12.194.9:3389` while workstation SSH remained
  blocked.
- Added a reusable Hyper-V PowerShell Direct reader and recorded the active
  `BB-WIN-LAB` RDP certificate directly from the guest certificate store.
- Independently recorded SHA-256
  `42cb09ef4c234542485e307afb32f00c9d0de063bcad077b94397c0a51f209b2`.
- Registered BrainConnect target
  `0efb72ab-7b55-481a-914b-f689f427dfef` disabled by default.
- Probed the live Windows endpoint through the Pi's native FreeRDP 3.26 helper.
  The exact certificate matched, with `authenticated = false` and
  `desktop_session_started = false`.
- Verified append-only audit sequences 29 through 31 for registration,
  identity verification, and explicit enablement.
- Enabled the exact target only after the independent identity matched.
- Revoked and rotated the Pi controller token after it appeared in malformed
  diagnostic command output. The replacement remained private on the Pi;
  authenticated health returned 200 and unauthenticated health returned 401.
- Published BrainConnect revision `654795b` to draft pull request 7.

## Decisions made

- Treat Hyper-V PowerShell Direct plus the guest certificate store as the
  independent RDP identity path, separate from BrainConnect and FreeRDP.
- Treat any controller token printed in diagnostic output as compromised and
  rotate it before continuing, even when exposure is limited to local tooling.

## Current blockers

- Observation-only FreeRDP frame delivery is not implemented.
- A controlled external credential/session provider is required before live
  Windows frames can be obtained; no credential may enter the target record,
  repository, Flutter asset, command line, or audit payload.
- The detached answer ISO still contains the one-time lab password and remains
  retained for recovery pending an explicit cleanup decision.
- A stale generated `controller/.pytest-tmp` directory has a Windows ACL lock;
  backend tests pass using an isolated operating-system temporary directory.

## Immediate next step

Define and implement the versioned, bounded, redacted, observation-only frame
protocol against a deterministic fixture. Keep authentication, input, and all
RDP redirection capabilities outside that first implementation.

## Long-term objective

Operate a resettable Windows research target that BrainConnect can observe
through a certificate-pinned, memory-bounded, redacted transport with
auditable state transitions and checkpoint restoration between experiments.
