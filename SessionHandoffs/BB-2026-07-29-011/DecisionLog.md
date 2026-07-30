# Decision Log

## BB-ADR-039

- **Date:** 2026-07-29
- **Decision:** Require both persisted execution configuration and
  authenticated live health to prove an inert installed controller before
  upgrade.
- **Reason:** The previous promotion reached its final check while the
  reviewed execution drop-in was still enabled. A file-only or health-only
  check can disagree with effective state.
- **Alternatives considered:** Rely only on the systemd drop-in, rely only on
  controller health, stop the service automatically, or allow the installer
  to repair state after upload.
- **Chosen solution:** Run a read-only preflight before wheel construction or
  upload. Refuse an enabled drop-in. If the service is active, require
  authenticated production health with `executor_enabled=false` and the
  emergency stop armed.
- **Impact:** Controller upgrades fail before mutation when live execution is
  possible or cannot be confidently ruled out.

## BB-ADR-040

- **Date:** 2026-07-29
- **Decision:** Separate low-impact daytime tasks from resource-intensive
  nightshift verification.
- **Reason:** Pi promotion, VM checkpoint work, Flutter analysis, and
  cross-architecture builds can consume resources or interrupt the lab while
  operator decisions and focused tests do not.
- **Alternatives considered:** Run the entire sequence immediately, pause all
  work until nightshift, or track the split only in chat.
- **Chosen solution:** Keep decisions, documentation, and focused local tests
  in the daytime lane; preserve the ordered heavy sequence in the canonical
  Master TODO and this session handoff.
- **Impact:** Progress continues without degrading daytime responsiveness, and
  the heavy verification sequence remains durable and discoverable.
