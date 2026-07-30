# Execution Plan

## Phase 1 - Observation contract

1. Specify a fixed, bounded, redacted frame or region response.
2. Keep the observation path read-only and separate from input credentials.
3. Define cursor metadata, framebuffer, and visible-text verification results.

## Phase 2 - Compatibility

1. Reconcile FreeRDP 3.15.x build settings with the Pi 3.26.0 runtime.
2. Add an explicit on-host compatibility test for every setting used by
   authentication, session selection, and input delivery.
3. Preserve amd64 and arm64 warnings-as-errors builds.

## Phase 3 - Bounded live proof

1. Restore the exact checkpoint and re-probe the certificate.
2. Capture a bounded before observation.
3. Execute one absolute pointer move and verify the cursor or frame delta.
4. Execute one keyboard sequence and verify visible contents.
5. Record transport and observed-state results separately.

## Phase 4 - Rollback and handoff

1. Disable execution and remove all temporary credentials and runners.
2. Restore the exact checkpoint and verify the Pi is inert.
3. Update BrainConnect canonical documentation.
4. Update BoxBrain indexes and create the next session handoff.
