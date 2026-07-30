# Decision Log

## BB-ADR-009

- **Date:** 2026-07-28
- **Decision:** Isolate RDP certificate observation behind a versioned,
  fail-closed helper protocol. Permit an authenticated operator to probe a
  registered disabled target before approval. An observed mismatch atomically
  disables an enabled target; helper and protocol failures are audited without
  changing target authority.
- **Reason:** BrainConnect must independently verify endpoint identity before
  credentials or frame delivery while keeping native network parsing outside
  the FastAPI process. Pre-approval probing is necessary to compare the live
  certificate with a separately trusted fingerprint.
- **Alternatives considered:** Link FreeRDP directly into the controller,
  execute a generic FreeRDP command with caller-selected flags, allow probes
  only after enablement, use trust-on-first-use or certificate-ignore behavior,
  and disable targets after every helper failure.
- **Chosen solution:** Invoke only an administrator-configured absolute helper
  path with a fixed argument array, no command shell, a minimal environment,
  bounded timeout, and strict schema version 1 JSON. Require explicit
  `authenticated: false` and `desktop_session_started: false` claims. Keep the
  plugin disabled until a native helper is separately built and configured.
- **Impact:** The controller, audit store, and Flutter UI can exercise the
  complete identity-verification workflow with deterministic test doubles.
  Missing or invalid helpers fail closed. Native FreeRDP code can be built,
  versioned, and replaced independently without duplicating target policy.
