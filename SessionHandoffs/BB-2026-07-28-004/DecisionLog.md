# Decision Log

## BB-ADR-008

- **Date:** 2026-07-28
- **Decision:** Persist target identity separately from authority. Registration
  creates a disabled record with an immutable UUID and exact SHA-256
  certificate fingerprint; enablement requires fingerprint re-entry and a
  written reason; task creation requires an enabled target UUID.
- **Reason:** Stored identity must not implicitly authorize network activity,
  and task admission needs a durable safety boundary before any remote
  transport is implemented.
- **Alternatives considered:** Configuration-file-only targets, implicit
  enablement on registration, host-and-port identity, and free-form target
  strings on tasks.
- **Chosen solution:** Use an additive SQLite target table with normalized,
  unique endpoints, disabled-by-default state, explicit audited lifecycle
  operations, and an enabled-target task gate.
- **Impact:** Existing alpha databases migrate without losing task or audit
  data. Credentials remain outside the registry. Future observation plugins
  must compare the live certificate with the approved fingerprint and disable
  the target on mismatch.
