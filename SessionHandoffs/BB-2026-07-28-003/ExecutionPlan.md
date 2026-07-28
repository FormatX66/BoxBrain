# Execution Plan

## 1. Published verified foundation

1. [x] Push BrainConnect `main`.
2. [x] Push `feature/brainconnect-live-events`.
3. [x] Integrate the canonical BoxBrain history into a branch based on the existing
   remote main branch.
4. [x] Resolve overlapping root documentation while preserving both histories.
5. [x] Validate and push `codex/repository-organization`.
6. [x] Open draft reviews for BrainConnect and BoxBrain.

## 2. Implement the target registry

1. Add durable target persistence and migration.
2. Add strict typed validation.
3. Add authenticated, audited lifecycle endpoints.
4. Gate task creation on enabled targets.
5. Add the Flutter target-management workflow.
6. Verify and document.

## 3. Implement observation

1. Define the fixed FreeRDP process invocation.
2. Implement certificate probe and exact fingerprint verification.
3. Deliver redacted frames without input or redirection capabilities.
4. Enforce memory-only raw frames and bounded evidence retention.
5. Add identity-mismatch rejection, auto-disable, and audit coverage.

## Completion gates

- No duplicate repository or canonical document is introduced.
- No credentials or raw frames enter durable target records.
- No keyboard, pointer, clipboard, file, shell, or device-redirection path is
  enabled.
- All project tests and BoxBrain validation pass.
