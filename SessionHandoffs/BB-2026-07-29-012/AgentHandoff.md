# Agent Handoff

## Current Objective

Run the queued nightshift gates for BrainConnect revision `494ec3f`, promote
scrolling only if every gate passes, and independently verify one visible
scroll effect.

## Tasks

1. Confirm the workstation is in the nightshift window.
2. Verify both repositories are clean and revision `494ec3f` is pushed.
3. Run the full controller and Flutter suites.
4. Build and test native 0.3.0 for amd64 and arm64 with warnings as errors.
5. Confirm the Pi is inert and exercise enabled-refusal plus disabled-success
   controller-upgrade preflight paths.
6. Run exact FreeRDP 3.26 identity, credential-negative, protocol, and wheel
   gates on the Pi.
7. Restore `clean-linked-rotated-2026-07-29` and re-probe its certificate.
8. Create deterministic scrollable target content, capture a bounded before
   frame, send one coordinate-bound scroll, and capture an after frame.
9. Disable execution, remove credentials, drop-ins, and temporary runners,
   restore the checkpoint, and verify final inert state.

## Dependencies

- BrainConnect revision `494ec3f`
- BrainConnect draft pull request
  [12](https://github.com/FormatX66/BrainConnect/pull/12)
- Installed controller revision `567ffa3`
- Pi controller `10.12.194.1:8000`
- Windows target `10.12.194.9:3389`
- Target UUID `0efb72ab-7b55-481a-914b-f689f427dfef`
- Verified checkpoint `clean-linked-rotated-2026-07-29`
- Exact target certificate and credential workflow recorded in session
  `BB-2026-07-29-010`

## Files affected

- BrainConnect native artifact provenance and any compatibility fixes
- BrainConnect deployment, security, roadmap, and live-evidence documentation
- BoxBrain project, decision, change, session, and verification indexes

## Required repositories

- `https://github.com/FormatX66/BrainConnect`
- `https://github.com/FormatX66/BoxBrain`

## Verification checklist

- Full controller and Flutter gates pass.
- Native protocol tests verify +120 as `0x078` and -120 as `0x188`.
- Native amd64 and arm64 builds pass with warnings as errors.
- Real-Pi upgrade preflight refuses enabled execution before mutation.
- Exact Pi FreeRDP 3.26 gates pass before installation.
- Installed provenance names `pointer_scroll` and records exact hashes.
- Before/after bounded frames independently show the scrolling effect.
- Final controller reports `executor_enabled=false` with stop armed.
- Execution drop-in, encrypted credentials, and temporary runners are absent.
- Rotated checkpoint is restored; retired checkpoint is untouched.

## Suggested commit message

`Verify bounded RDP scrolling on the Pi`

## Suggested branch

`feature/brainconnect-rdp-input-verification`

## Potential risks

- FreeRDP 3.15 build and 3.26 runtime behavior may differ for horizontal wheel
  capability negotiation.
- Transport acceptance alone cannot prove that the intended window scrolled.
- An incorrect absolute location could scroll the wrong control.
- Pi or VM work outside the nightshift window could interfere with normal use.

## Estimated completion order

1. Full local verification
2. Native cross-builds
3. Pi upgrade and compatibility gates
4. Rotated-checkpoint live proof
5. Cleanup and final verification
6. Documentation, commit, push, and next handoff
