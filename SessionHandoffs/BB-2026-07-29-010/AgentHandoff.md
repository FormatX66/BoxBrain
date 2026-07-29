# Agent Handoff

## Current Objective

Make controller upgrades fail closed when RDP execution is active, then extend
the verified native capability set without weakening the exact-target
boundary.

## Tasks

1. Start from `clean-linked-rotated-2026-07-29`.
2. Add an authenticated or systemd-state preflight to the Pi controller
   installer that refuses upgrade while the open-lab executor is enabled.
3. Add tests for enabled-drop-in refusal and disabled-upgrade success.
4. Decide whether shell, scrolling, or clipboard is the next native operation.
5. Preserve bounded frame or guest-state verification for each live effect.
6. Keep the Pi inert between bounded runs.
7. Do not restore `clean-linked-2026-07-29`.

## Dependencies

- BrainConnect documentation revision `f4461d2` on
  `feature/brainconnect-rdp-input-verification`
- Installed BrainConnect revision `567ffa3`
- BrainConnect draft pull request
  [12](https://github.com/FormatX66/BrainConnect/pull/12)
- Installed control SHA-256
  `090929ac598855b5da72732a08975a291fa84d4cfbb718585665c8c747c5077e`
- Pi controller `10.12.194.1:8000`
- Windows target `10.12.194.9:3389`
- Target UUID `0efb72ab-7b55-481a-914b-f689f427dfef`
- Pinned certificate SHA-256
  `42cb09ef4c234542485e307afb32f00c9d0de063bcad077b94397c0a51f209b2`
- Verified checkpoint `clean-linked-rotated-2026-07-29`
- Retired checkpoint `clean-linked-2026-07-29`

## Files affected

- BrainConnect Pi controller installer and tests
- BrainConnect selected native operation, protocol, UI, and tests
- BrainConnect deployment and security documentation
- BoxBrain project index, admin indexes, architecture, and next handoff

## Required repositories

- `https://github.com/FormatX66/BrainConnect`
- `https://github.com/FormatX66/BoxBrain`

## Verification checklist

- Upgrade preflight rejects an enabled executor before installing files.
- Disabled upgrades still pass the authenticated foreground and service gates.
- Exact revision and native hashes are recorded.
- Controller and Flutter tests pass.
- Native amd64 and arm64 tests pass.
- Any live run starts from the rotated checkpoint.
- Certificate probe remains exact and unauthenticated.
- Operation effect is independently verified.
- Executor, drop-in, credentials, and temporary runners are absent afterward.
- Retired checkpoint is never restored.

## Suggested commit message

`Refuse controller upgrades during live execution`

## Suggested branch

`feature/brainconnect-upgrade-preflight`

## Potential risks

- A preflight based only on a file can disagree with effective systemd state.
- An authenticated health preflight depends on a healthy old controller.
- FreeRDP 3.15 build and 3.26 runtime differences can affect new operations.
- Clipboard and shell capabilities expand data exposure more than scrolling.
- Deleting the retired checkpoint without a reviewed merge plan can damage the
  current checkpoint chain.

## Estimated completion order

1. Upgrade-state contract
2. Installer tests
3. Pi disabled-upgrade dry run
4. Next capability selection
5. Native/controller/UI implementation
6. amd64 and arm64 gates
7. Rotated-checkpoint live verification
8. Cleanup and next handoff
