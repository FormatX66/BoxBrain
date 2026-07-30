# Execution Plan

## Milestone 1 - Credential and session boundary

1. Choose a runtime-only credential provider.
2. Define the dedicated lab account and rotation procedure.
3. Prove no secret appears in arguments, environment, controller state, logs,
   or audit events.
4. Add an authenticate/verify/disconnect self-test with no input.

## Milestone 2 - FreeRDP live connector

1. Build against the pinned FreeRDP baseline.
2. Reuse strict certificate callbacks and reject every changed identity.
3. Correlate the authenticated desktop session with the requested target.
4. Emit only version 1 result objects.

## Milestone 3 - First typed input

1. Implement one pointer move or harmless key action.
2. Add hard timeout, cancellation, and cleanup.
3. Capture bounded before/after evidence and verify the state change.
4. Exercise identity mismatch, credential failure, timeout, disconnect, and
   emergency stop.

## Milestone 4 - Capability expansion

1. Complete pointer and keyboard operations.
2. Add clipboard read/write with transient content.
3. Select and implement the shell transport.
4. Keep drive, file, device, printer, camera, microphone, and audio redirection
   disabled.

## Milestone 5 - Controlled experiment

1. Confirm exact target and clean checkpoint.
2. Install the reviewed connector but keep it disabled.
3. Enable it for one manual operation.
4. Record result and evidence.
5. Classify failures and constrain only the responsible capability.
6. Restore and verify `clean-linked-2026-07-29`.
7. Update BrainConnect, BoxBrain, and the next session handoff.
