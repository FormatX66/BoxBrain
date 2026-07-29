# Execution Plan

## Milestone 1 - Read-only Windows session diagnosis

1. Sign out and back in once so Hyper-V Administrators membership becomes
   available to the operator token.
2. Restore `clean-linked-2026-07-29` and re-probe the certificate.
3. Use PowerShell Direct to record session IDs, users, states, lock state,
   `fSingleSessionPerUser`, and recent Terminal Services events.
4. Correlate those records with one no-input FreeRDP connection.

## Milestone 2 - Smallest session-routing fix

1. Decide whether FreeRDP settings, username/domain identity, reconnect
   behavior, or a lab Windows policy causes the new LogonUI sessions.
2. Change only the evidenced layer.
3. Preserve exact target, NLA/HYBRID, certificate, redirection, sequence, and
   credential gates.
4. Add a regression fixture for the chosen session behavior where practical.

## Milestone 3 - Verified input run

1. Restore and re-probe.
2. Verify Notepad is absent.
3. Install credentials with execution disabled.
4. Enable one short window and execute one launch/type sequence.
5. Require Notepad process presence as the first independent result.
6. Optionally add bounded text-content evidence after process proof works.

## Milestone 4 - Rollback and handoff

1. Disable execution and remove all encrypted credentials.
2. Verify active controller, armed emergency stop, absent drop-in, and zero
   credential files.
3. Restore the clean checkpoint and re-probe its certificate.
4. Update BrainConnect, BoxBrain, pull-request evidence, and the next handoff.
