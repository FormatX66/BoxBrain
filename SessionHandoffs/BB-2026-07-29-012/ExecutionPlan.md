# Execution Plan

## Daytime lane - complete

1. Select pointer scrolling.
2. Define explicit coordinates, 120-unit steps, and a ten-step budget.
3. Wire controller, dashboard, native source, installer provenance, and runner.
4. Run only focused Python tests and syntax/format checks.
5. Commit and push without touching the live lab or heavy toolchains.

## Nightshift lane - ordered heavy work

1. Confirm the workstation is free for resource-intensive work.
2. Run the complete controller suite and Flutter analysis/tests.
3. Build native 0.3.0 for amd64 and arm64 with warnings as errors; run every
   protocol, credential, identity, frame, and integration test.
4. Confirm the Pi is inert. Exercise upgrade refusal with execution enabled,
   then disabled-success promotion with exact provenance.
5. Run the native identity/credential-negative fixture against FreeRDP 3.26.
6. Restore `clean-linked-rotated-2026-07-29`, re-probe the certificate, and
   prepare deterministic numbered scroll content.
7. Capture a bounded before frame, execute one vertical scroll at explicit
   coordinates, capture an after frame, and compare visible state.
8. Disable execution, remove the drop-in, credentials, and temporary runners,
   restore the rotated checkpoint, and verify final identity and health.
9. Update documentation, validate both repositories, commit, push, and create
   the next handoff.

## Stop conditions

- Stop if daytime computer use resumes.
- Stop before mutation if upgrade configuration and live health disagree.
- Stop if native tests or exact Pi-runtime gates fail.
- Stop if the target certificate differs.
- Stop if the VM is not at the rotated checkpoint.
- Stop if any credential appears in output or repository state.
- Never restore or delete `clean-linked-2026-07-29`.
