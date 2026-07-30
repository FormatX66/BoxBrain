# Execution Plan

## Milestone 1 - Restore the disposable target

1. Use an authorized Hyper-V identity to restore
   `clean-linked-2026-07-29`.
2. Confirm VM network and restricted diagnostic health.
3. Read and re-probe the RDP certificate.
4. Reapprove the target only if its independently read identity matches.

## Milestone 2 - Persistent bounded input

1. Define one versioned persistent-session sequence.
2. Cap events, text, repeats, duration, and inter-event delay.
3. Retain exact target UUID, endpoint, certificate, and NLA checks.
4. Keep arbitrary scancodes, shell arguments, and every FreeRDP redirection
   unavailable.
5. Test timeout, disconnect, malformed sequence, and partial-send behavior.

## Milestone 3 - Independent verification

1. Choose bounded frame evidence, a non-sensitive guest marker, or both.
2. Record precondition, expected state, and observed state separately.
3. Keep raw pixels or guest output transient unless redacted evidence is
   explicitly selected.
4. Report transport acceptance and verified state change as different fields.

## Milestone 4 - Live run and rollback

1. Install credentials while execution remains disabled.
2. Enable one bounded run.
3. Execute one harmless persistent-session sequence.
4. Collect independent state evidence.
5. Disable execution and remove all encrypted credentials.
6. Verify controller health, emergency stop, absent drop-in, and zero
   credential files.
7. Update BrainConnect, BoxBrain, review status, and the next handoff.
