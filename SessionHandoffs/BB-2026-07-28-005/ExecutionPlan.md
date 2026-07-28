# Execution Plan

## 1. Completed certificate-probe boundary

1. [x] Define the fixed helper invocation and schema version 1 response.
2. [x] Add strict process, timeout, output, endpoint, and safety validation.
3. [x] Add the authenticated probe API and emergency-stop gate.
4. [x] Audit matches and bounded failures.
5. [x] Atomically disable enabled targets after identity mismatch.
6. [x] Add the Flutter probe workflow.
7. [x] Verify controller, Flutter, and production web build.
8. [x] Commit, push, and open stacked draft pull request 3.

## 2. Build the native FreeRDP helper

1. Pin a reproducible FreeRDP 3.x, CMake, and compiler baseline.
2. Implement only the fixed version 1 argument parser.
3. Register the X.509 verification callback.
4. Serialize bounded certificate metadata and abort before authentication.
5. Prohibit all input, clipboard, file, shell, audio, print, drive, and device
   redirection.
6. Add native unit tests and isolated-lab integration tests.
7. Package the helper separately and configure its absolute path.

## 3. Implement observation frames

1. Start only after the native certificate probe is verified.
2. Deliver redacted frames without input or redirection capabilities.
3. Enforce memory-only raw frames and bounded evidence retention.
4. Add deterministic restart, expiry, and audit coverage.

## Completion gates

- No duplicate repository or canonical document is introduced.
- The native helper conforms to the existing version 1 protocol.
- No credentials, desktop session, raw frames, or input capability enter the
  certificate-probe milestone.
- All native, controller, Flutter, and BoxBrain validation passes.
