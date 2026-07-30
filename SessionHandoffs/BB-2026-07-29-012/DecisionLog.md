# Decision Log

## BB-ADR-041

- **Date:** 2026-07-29
- **Decision:** Select scrolling before shell or clipboard and bind every
  scroll to absolute coordinates plus at most ten standard wheel steps.
- **Reason:** Scrolling expands useful navigation without introducing shell
  execution or clipboard data transfer. A stateless RDP connector cannot
  safely assume the cursor remains over the intended control.
- **Alternatives considered:** Implement shell first, implement clipboard
  first, scroll at the cursor's prior position, accept arbitrary wheel units,
  or allow an unbounded number of wheel events.
- **Chosen solution:** Require absolute X/Y, move and scroll in one pinned
  connection, accept only 120-unit steps, and limit combined horizontal and
  vertical motion to 1,200 units.
- **Impact:** Each request emits at most ten deterministic wheel events and
  adds no new target-data return path. Cross-build and live proof remain
  mandatory before promotion.
