# Agent Handoff

## Current Objective

Add a bounded observation path that can independently verify cursor position
and visible text after BrainConnect input operations.

## Tasks

1. Start from the clean `clean-linked-2026-07-29` checkpoint.
2. Re-probe the exact certificate before any execution window.
3. Define a small, redacted frame or region-of-interest observation result.
4. Keep observation separate from the credentialed input connector.
5. Align the native FreeRDP build with Pi runtime 3.26.0, or add a tested
   compatibility gate for the current 3.15.x build.
6. Verify one absolute pointer move with cursor or frame evidence.
7. Verify one keyboard sequence with visible text-content evidence.
8. Return the Pi to its inert state and restore the exact checkpoint.

## Dependencies

- BrainConnect commit `379f4dc` on
  `feature/brainconnect-rdp-input-verification`
- BrainConnect functional input revision `871fe43`
- BrainConnect draft pull request
  [12](https://github.com/FormatX66/BrainConnect/pull/12)
- Installed control SHA-256
  `592feb4b12fb5c7a6066cae6433495ecbc050647ebff90a0ea4d26ec19c3432d`
- Pi controller `10.12.194.1:8000`
- Windows target `10.12.194.9:3389`
- Target UUID `0efb72ab-7b55-481a-914b-f689f427dfef`
- Pinned certificate SHA-256
  `42cb09ef4c234542485e307afb32f00c9d0de063bcad077b94397c0a51f209b2`
- Checkpoint `clean-linked-2026-07-29`

## Files affected

- BrainConnect observation plugin and protocol
- BrainConnect native build/runtime compatibility tests
- BrainConnect experiment verifier and deployment documentation
- BoxBrain architecture, project index, admin indexes, and next handoff

## Required repositories

- `https://github.com/FormatX66/BrainConnect`
- `https://github.com/FormatX66/BoxBrain`

## Verification checklist

- Exact checkpoint is restored before and after the run.
- Certificate probe remains exact and unauthenticated.
- Observation payload is bounded and redacted.
- Cursor or region evidence is captured before and after pointer input.
- Text content is verified independently of input transport.
- Executor window is short, audited, and disabled afterward.
- Execution drop-in, temporary runners, and encrypted credentials are absent.
- Controller token and target password never appear in logs or output.
- Final controller health reports the executor disabled.

## Suggested commit message

`Add verified RDP frame observation`

## Suggested branch

`feature/brainconnect-frame-verification`

## Potential risks

- Screenshots can capture sensitive information unless the region and
  retention policy are strict.
- Cursor rendering may be separate from the desktop framebuffer.
- Build/runtime FreeRDP drift can change option semantics.
- A process check proves launch but not focus, cursor, or text correctness.
- A failed cleanup can leave credentials or an execution drop-in active.

## Estimated completion order

1. Observation protocol and privacy limits
2. FreeRDP build/runtime alignment
3. Unit and synthetic frame tests
4. amd64 and arm64 artifact gates
5. Clean restore and certificate probe
6. Short pointer and keyboard live verification
7. Credential/executor rollback and final restore
8. Documentation and handoff
