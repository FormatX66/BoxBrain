# Project Updates

## BrainConnect

- **Status:** Active alpha
- **Completion:** 98% planning estimate
- **Current revision:** `494ec3f`
- **Installed revision:** `567ffa3`
- **Source complete:** Coordinate-bound pointer scrolling, standard signed
  wheel encoding, ten-step budget, controller/dashboard/native wiring,
  provenance, runner support, and focused tests.
- **Pending nightshift:** Full controller/Flutter gates, native amd64/arm64
  builds, Pi upgrade preflight, exact FreeRDP 3.26 tests, promotion, live frame
  proof, and cleanup.

## BoxBrain

- Recorded pointer scrolling as the selected next capability.
- Recorded decision BB-ADR-041.
- Replaced the general capability choice with a scrolling-specific nightshift
  sequence.

## Related projects

- **Security:** Scrolling adds no new target-data return path and is bounded to
  ten standard events.
- **Research:** Before/after frame evidence can become the first scrolling
  benchmark case.
- **Automation:** Nightshift orchestration remains future work requiring
  explicit scheduling authorization.
