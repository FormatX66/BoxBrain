# Execution Plan

## 1. Completed target registry

1. [x] Add durable target persistence and schema migration.
2. [x] Add strict typed validation and normalized endpoint uniqueness.
3. [x] Add authenticated, audited lifecycle endpoints.
4. [x] Gate task creation on enabled target UUIDs.
5. [x] Add the Flutter target-management workflow.
6. [x] Verify controller, Flutter, and production web build.
7. [x] Commit, push, and open stacked draft pull request 2.

## 2. Implement the observation probe

1. Define the fixed FreeRDP executable and argument contract.
2. Implement an out-of-process certificate-only probe.
3. Compare observed and approved certificate fingerprints.
4. Reject and disable targets after any identity mismatch.
5. Audit success, mismatch, timeout, and process-failure outcomes.
6. Verify the probe never submits credentials or establishes a desktop
   session.

## 3. Implement observation frames

1. Start only after the certificate probe is verified.
2. Deliver redacted frames without input or redirection capabilities.
3. Enforce memory-only raw frames and bounded evidence retention.
4. Add deterministic restart, expiry, and audit coverage.

## Completion gates

- No duplicate repository or canonical document is introduced.
- No credentials or raw frames enter durable target records.
- No keyboard, pointer, clipboard, file, shell, audio, print, drive, or
  device-redirection path is enabled.
- All project tests and BoxBrain validation pass.
