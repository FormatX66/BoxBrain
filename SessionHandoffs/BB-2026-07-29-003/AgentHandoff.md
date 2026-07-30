# Agent Handoff

## Current objective

Implement the first bounded observation-only frame contract without adding
credentials, input, redirection, persistence, or a controller executor.

## Tasks

1. Define a versioned frame response with dimensions, pixel format, sequence,
   timestamp, redaction status, and bounded payload size.
2. Set explicit cadence, memory, queue, timeout, retry, and backpressure
   limits.
3. Extend the native helper or add a separate observer process without
   weakening the existing certificate gate.
4. Keep keyboard, pointer, clipboard, drive, printer, serial, smart-card,
   microphone, camera, shell, and file transfer unavailable.
5. Prove deterministic fixture delivery, malformed-frame rejection,
   certificate mismatch, disconnect, timeout, and backpressure handling.
6. Define a separate credential/session provider before any live Windows frame
   test; never store its secret in the target registry or controller database.
7. Add redaction before any frame leaves the observer process.
8. Run a controlled live observation only after the fixture gate passes.
9. Restore and verify checkpoint `clean-linked-2026-07-29` after the live run.

## Dependencies

- BrainConnect revision `654795b`
- BrainConnect draft pull request
  [7](https://github.com/FormatX66/BrainConnect/pull/7)
- Pi controller at `10.12.194.1:8000`
- Enabled target `0efb72ab-7b55-481a-914b-f689f427dfef`
- Windows endpoint `10.12.194.9:3389`
- Independent certificate SHA-256
  `42cb09ef4c234542485e307afb32f00c9d0de063bcad077b94397c0a51f209b2`
- Identity verification timestamp `2026-07-29T16:01:56.395853Z`
- Clean Standard checkpoint `clean-linked-2026-07-29`
- RDP identity evidence:
  `C:\VMs\BoxBrain-Windows-Lab\rdp-certificate-identity.json`

## Files affected

- BrainConnect `README.md`
- BrainConnect `docs/ROADMAP.md`
- BrainConnect `docs/SECURITY.md`
- BrainConnect `docs/TARGETS.md`
- BoxBrain `sandbox/hyperv/Get-BoxBrainWindowsRdpIdentity.ps1`
- BoxBrain `sandbox/hyperv/README.md`
- BoxBrain admin, architecture, project, and session indexes
- BoxBrain `SessionHandoffs/BB-2026-07-29-003/`

## Required repositories

- `https://github.com/FormatX66/BrainConnect`
- `https://github.com/FormatX66/BoxBrain`

## Verification checklist

- Independent and observed certificate SHA-256 remain identical.
- Observer refuses every certificate change before authentication.
- Frame protocol has fixed schema and hard byte limits.
- Raw frames stay memory-only by default.
- Redaction occurs before delivery or persistence.
- No credential appears in arguments, logs, audit events, target records, or
  repository files.
- No input or redirection capability is present.
- Target failures remain bounded and audited.
- Clean checkpoint is restored after live observation.
- BrainConnect and BoxBrain tests and validation pass.

## Suggested commit message

`feat: add bounded RDP frame protocol`

## Suggested branch

`feature/brainconnect-rdp-frame-observer`

## Potential risks

- RDP frame delivery normally requires authentication even when input is
  disabled.
- A target marked enabled can admit queued tasks, although the current
  controller still has no executor.
- Frame pixels may disclose sensitive guest content before redaction.
- Unbounded frame cadence or queueing can exhaust Pi memory.
- Certificate rotation or checkpoint restore can invalidate the target
  identity and must disable the target.
- Ad hoc authenticated shell commands can expose tokens through quoting
  mistakes; use reviewed helpers and never print credentials.

## Estimated completion order

1. Frame schema and hard limits
2. Deterministic observer fixture
3. Native observer process
4. Controller validation and audit contract
5. Redaction and memory-only delivery
6. Flutter display without persistence
7. External credential/session design
8. Controlled live observation
9. Checkpoint restoration and handoff
