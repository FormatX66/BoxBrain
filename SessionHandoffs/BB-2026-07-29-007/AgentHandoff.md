# Agent Handoff

## Current Objective

Convert the proven transport-level pointer and keyboard path into
independently verified UI control by keeping a bounded RDP session alive across
one operation sequence and observing the resulting target state.

## Tasks

1. Restore and verify checkpoint `clean-linked-2026-07-29` using an authorized
   Hyper-V account.
2. Re-read and re-probe the target RDP certificate after restoration.
3. Design a versioned bounded sequence request or session token without
   permitting arbitrary FreeRDP arguments.
4. Keep one exact-target RDP connection active across its related key/text
   events.
5. Add observation-only frame evidence or a narrowly scoped guest-state
   verifier.
6. Record transport acceptance separately from verified target-state change.
7. Repeat one harmless input sequence in a short enablement window.
8. Disable the executor and remove all encrypted credentials immediately after
   the run.
9. Decide whether pointer button, scrolling, or shell should be the next
   independently implemented capability.

## Dependencies

- BrainConnect revision `e81f5f5`
- BrainConnect draft pull request
  [11](https://github.com/FormatX66/BrainConnect/pull/11)
- Pi controller at `10.12.194.1:8000`
- Controller deployment source revision `e9d88ff`
- Native connector source revision `fd2281e`
- Control SHA-256
  `1d91cf630e7b1f16f8c95bc871479218caa86a1e9d7d9aa8aa3aebdbaa59b74b`
- Windows target `10.12.194.9:3389`
- Target UUID `0efb72ab-7b55-481a-914b-f689f427dfef`
- Pinned certificate SHA-256
  `42cb09ef4c234542485e307afb32f00c9d0de063bcad077b94397c0a51f209b2`
- Checkpoint `clean-linked-2026-07-29`

## Files affected

- BrainConnect native input connector, protocol, fixtures, and Pi experiment
  runner
- BrainConnect controller execution result schema if verification becomes a
  first-class result
- BrainConnect open-lab, architecture, security, roadmap, and deployment docs
- BoxBrain admin, architecture, project, and session indexes

## Required repositories

- `https://github.com/FormatX66/BrainConnect`
- `https://github.com/FormatX66/BoxBrain`

## Verification checklist

- Restore the intended checkpoint before creating credentials.
- Re-probe and reapprove if the RDP certificate changes.
- Keep exact target UUID, endpoint, protocol, and certificate pin checks.
- Keep all FreeRDP redirections disabled.
- Keep credentials out of Git, arguments, ordinary environment values, API
  payloads, logs, and audit events.
- Prove the bounded session exits on success, timeout, or error.
- Prove unsupported key names and operation sequences fail closed.
- Distinguish transport acceptance from independent target-state verification.
- Keep the executor enabled only for the bounded run.
- Remove the drop-in and every encrypted credential afterward.
- Confirm `executor_enabled=false`, emergency stop armed, and controller health.

## Suggested commit message

`feat: verify bounded RDP input sequences`

## Suggested branch

`feature/brainconnect-rdp-input-verification`

## Potential risks

- A persistent session can broaden time and action scope if its hard limits are
  incomplete.
- A new RDP session can lock or displace the console session.
- Guest process presence may not prove that input caused the expected UI
  state.
- Frame capture can expose sensitive target pixels unless evidence is bounded
  and redacted.
- Checkpoint restoration may rotate the RDP certificate and invalidate the
  current approval.
- A failed cleanup could leave a credential or service drop-in active.

## Estimated completion order

1. Authorized checkpoint restore and certificate re-probe
2. Bounded persistent-session protocol and tests
3. Independent verifier
4. Pi build and disabled promotion
5. One live verified input sequence
6. Credential and executor rollback
7. Documentation, review, and next handoff
