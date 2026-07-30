# Agent Handoff

## Current Objective

Verify the new controller-upgrade guard on the real Pi during nightshift, then
implement the operator-selected native capability without weakening the
exact-target boundary.

## Tasks

1. Confirm the operator's next-capability choice.
2. Start with the Pi inert and the VM at
   `clean-linked-rotated-2026-07-29`.
3. Prove enabled-drop-in refusal without changing the installed revision.
4. Prove disabled-upgrade success and the existing foreground/service gates.
5. Run full controller, Flutter, amd64, arm64, and exact Pi-runtime gates.
6. Implement and independently verify the selected bounded capability.
7. Remove credentials, drop-ins, and runners and restore the rotated
   checkpoint.
8. Do not restore or delete `clean-linked-2026-07-29`.

## Dependencies

- BrainConnect revision `be0738c`
- BrainConnect draft pull request
  [12](https://github.com/FormatX66/BrainConnect/pull/12)
- Installed BrainConnect revision `567ffa3`
- Pi controller `10.12.194.1:8000`
- Windows target `10.12.194.9:3389`
- Target UUID `0efb72ab-7b55-481a-914b-f689f427dfef`
- Verified checkpoint `clean-linked-rotated-2026-07-29`
- Existing exact-target certificate and native-artifact records in session
  `BB-2026-07-29-010`

## Files affected

- BrainConnect Pi installer, selected operation protocol, controller, Flutter
  UI, native connector, tests, and canonical documentation
- BoxBrain Master TODO, project index, architecture if the capability boundary
  changes, and the next session handoff

## Required repositories

- `https://github.com/FormatX66/BrainConnect`
- `https://github.com/FormatX66/BoxBrain`

## Verification checklist

- Enabled execution refuses upgrade before package construction or upload.
- Disabled or fresh installation reaches the existing verification gates.
- Full controller and Flutter suites pass.
- Native amd64 and arm64 tests pass.
- Exact FreeRDP 3.26 Pi-runtime tests pass.
- The live proof starts and ends at the rotated checkpoint.
- Every operation has bounded before/after or guest-state evidence.
- Executor, drop-in, credentials, and temporary runners are absent afterward.

## Suggested commit message

`Add bounded RDP scrolling control`

## Suggested branch

`feature/brainconnect-rdp-input-verification`

## Potential risks

- The active old controller can be unhealthy even when its persisted
  execution setting is disabled; preflight must refuse that disagreement.
- FreeRDP build/runtime drift can surface only in the exact Pi gate.
- Shell and clipboard expose more target data than scrolling.
- Deleting the retired checkpoint can trigger a slow Hyper-V disk merge and
  must remain separately approved.

## Estimated completion order

1. Operator capability decision
2. Real-Pi preflight refusal and success gates
3. Full local and cross-architecture verification
4. Selected capability implementation
5. Rotated-checkpoint live proof
6. Cleanup and next handoff
