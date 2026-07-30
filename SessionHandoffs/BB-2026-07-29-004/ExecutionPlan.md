# Execution Plan

## Milestone 1 - Adapter contract

1. Specify versioned request and result schemas.
2. Define hard input, output, timeout, retry, and evidence limits.
3. Define operation failure categories and interruption recovery.
4. Define target and desktop-session correlation requirements.

## Milestone 2 - Controller state machine

1. Add atomic claim of one queued operation.
2. Recheck emergency stop, task, target, endpoint, and certificate.
3. Add bounded `running`, terminal, and interrupted state transitions.
4. Add content-safe request, result, and verification audit events.

## Milestone 3 - External credentials

1. Choose a runtime-only credential provider.
2. Ensure secrets never enter Git, SQLite, API requests, process arguments, or
   audit output.
3. Add rotation and adapter-restart tests.

## Milestone 4 - Deterministic execution tests

1. Implement a fake adapter for every operation kind.
2. Test timeout, disconnect, malformed result, emergency stop, and target
   disablement.
3. Test modifier-key cleanup and pointer normalization.
4. Prove one-operation-at-a-time dispatch and hard limits.

## Milestone 5 - Controlled live experiment

1. Confirm checkpoint and exact target identity.
2. Enable the adapter explicitly.
3. Run one low-impact operation.
4. Capture bounded result and evidence.
5. Classify failures and constrain only the responsible capability or
   parameter.
6. Restore and verify `clean-linked-2026-07-29`.
7. Update BrainConnect, BoxBrain, and the next session handoff.
