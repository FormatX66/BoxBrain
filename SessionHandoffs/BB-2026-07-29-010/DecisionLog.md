# Decision Log

## BB-ADR-034

- **Date:** 2026-07-29
- **Decision:** Limit live frame observation to a caller-bounded, memory-only
  160-by-90 PPM region with cursor metadata and a verified pixel hash.
- **Reason:** Input effects required visual evidence without creating a
  general screenshot stream or durable image store.
- **Alternatives considered:** Full-screen capture, OCR-only verification,
  process checks only, and persistent screenshots.
- **Chosen solution:** Validate the region, cursor bounds, PPM structure,
  canonical Base64, byte length, and SHA-256 before transient return.
- **Impact:** Visible text and pointer effects can be independently verified
  with a small, content-bounded observation.

## BB-ADR-035

- **Date:** 2026-07-29
- **Decision:** Use the standard target-user RDP session and wait ten seconds
  for desktop readiness before observing or sending input.
- **Reason:** Bounded frames showed the console path at LogonUI and the standard
  session black during the prior one-second window.
- **Alternatives considered:** Console-session forcing, password keystrokes,
  arbitrary retries, longer post-input delays, and treating transport
  acceptance as success.
- **Chosen solution:** Establish or reconnect the standard session and service
  the RDP event loop for a fixed readiness window.
- **Impact:** The exact disposable desktop consistently receives keyboard,
  pointer, and frame operations.

## BB-ADR-036

- **Date:** 2026-07-29
- **Decision:** Reserve native standard output exclusively for one canonical
  JSON result and redirect FreeRDP diagnostics to standard error.
- **Reason:** FreeRDP informational lines contaminated the adapter protocol and
  caused the controller to report a false HTTP 502.
- **Alternatives considered:** Parse around arbitrary log text, suppress
  FreeRDP logging globally, or loosen controller JSON validation.
- **Chosen solution:** Temporarily isolate native diagnostic output and emit
  only the final result object on standard output.
- **Impact:** The controller retains strict fail-closed response validation
  without hiding transport diagnostics from operators.

## BB-ADR-037

- **Date:** 2026-07-29
- **Decision:** Require absolute X/Y coordinates on every pointer-button
  request and execute move plus button atomically in one connection.
- **Reason:** The connector creates a fresh RDP connection per operation, so a
  button-only event cannot safely rely on prior cursor state.
- **Alternatives considered:** Stateful sessions, separate pointer move and
  click operations, implicit cursor coordinates, and transport-only proof.
- **Chosen solution:** Bind button, action, X, Y, and absolute coordinate space
  into one strict operation.
- **Impact:** Clicks are deterministic across stateless operations and can be
  independently verified by later frame or guest-state evidence.

## BB-ADR-038

- **Date:** 2026-07-29
- **Decision:** Immediately rotate a disposable lab credential exposed in
  diagnostic output, retire every checkpoint containing its old state, and
  create a new verified recovery checkpoint.
- **Reason:** A credential value appearing in tool output must be treated as
  compromised even inside the disposable lab.
- **Alternatives considered:** Continue using the value, redact only future
  output, delete all checkpoints immediately, or rebuild the VM.
- **Chosen solution:** Rotate and verify the account, provision the replacement
  only through encrypted runtime files, retire the old checkpoint, and create
  `clean-linked-rotated-2026-07-29`.
- **Impact:** The exposed value is inactive. The old checkpoint remains
  retained but forbidden until an operator approves a safe Hyper-V
  delete/merge action.
