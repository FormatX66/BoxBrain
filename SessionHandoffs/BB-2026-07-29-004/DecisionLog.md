# Decision Log

## BB-ADR-021

- **Date:** 2026-07-29
- **Decision:** Start disposable-VM control capability-first, while retaining
  exact-target containment, audit, emergency stop, hard limits, external
  credentials, and checkpoint recovery.
- **Reason:** The VM is disposable and checkpointed. Beginning with the broad
  target-local operation set makes it possible to observe real transport,
  timing, UI-state, and application failures, then remove or constrain only
  the features that evidence shows are problematic.
- **Alternatives considered:**
  - Build observation-only frames before any control operation.
  - Enable keyboard and pointer first, then add shell and clipboard later.
  - Remove all policy and containment checks in the sandbox.
- **Chosen solution:** Queue all eight bounded operation types under the
  `open` profile, keep `safe` and `research` without control capabilities, and
  leave live execution disabled until a reviewed VM-only adapter exists.
- **Impact:** BrainConnect now has a real durable control contract and usable
  dashboard forms. The next milestone is an executor adapter and result
  protocol, not more queue design. Outer containment is still enforced, so
  “open” does not grant authority over the controller host, Pi, workstation,
  or other targets.
