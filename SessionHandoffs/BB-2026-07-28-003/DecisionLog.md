# Decision Log

## BB-ADR-006

- **Date:** 2026-07-28
- **Decision:** Use an out-of-process FreeRDP 3.x observer with immutable target
  UUIDs, exact SHA-256 server-certificate pins, disabled-by-default approval,
  automatic disable on identity mismatch, and bounded evidence retention.
- **Reason:** The alpha target is Windows, RDP provides TLS server identity,
  and FreeRDP exposes certificate and changed-certificate verification hooks.
- **Alternatives considered:** VNC, HDMI capture, and host/port-only identity.
- **Chosen solution:** RDP/FreeRDP for the first network observer; VNC is
  deferred and hardware capture remains a separate adapter class.
- **Impact:** The target registry can be implemented without enabling input.
  Credential storage, certificate bypasses, and `/cert:ignore` are prohibited.

## BB-ADR-007

- **Date:** 2026-07-28
- **Decision:** Consolidate the canonical organization into the existing
  `FormatX66/BoxBrain` repository through `codex/repository-organization`.
- **Reason:** The remote already contains 29 commits of BoxBrain application
  history, and replacing its `main` branch would violate preservation and
  non-duplication rules.
- **Alternatives considered:** Create a second BoxBrain repository, force-push
  the local history, or leave the organization local-only.
- **Chosen solution:** Merge the unrelated canonical history into a branch
  based on the remote main branch, resolve only overlapping root documents,
  and submit it for review.
- **Impact:** One remote remains authoritative and all prior application history
  is preserved. The review branch must be merged before the organization is on
  remote `main`.
