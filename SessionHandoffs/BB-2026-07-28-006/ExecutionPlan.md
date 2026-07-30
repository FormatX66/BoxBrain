# Execution Plan

## 1. Completed native certificate helper

1. [x] Pin Debian 13, FreeRDP 3.15.x, CMake, GCC, and OpenSSL.
2. [x] Implement strict fixed arguments and bounded schema version 1 JSON.
3. [x] Extract certificate metadata through external certificate management.
4. [x] Require exact server-selected NLA/HYBRID.
5. [x] Reject TLS-only downgrade and every presented certificate.
6. [x] Fail on authentication, `PostConnect`, or deadline overrun.
7. [x] Build and pass native tests on amd64 and arm64.
8. [x] Reverify controller and Flutter applications.
9. [x] Commit, push, and open stacked draft pull request 4.

## 2. Package and live-test the helper

1. Select an isolated disposable Windows RDP target.
2. Build an amd64 and/or arm64 package from the pinned source and image.
3. Record source revision, dependencies, provenance, and checksums.
4. Install on an isolated Linux/Pi controller and configure the absolute path.
5. Run exact-match, changed-certificate, timeout, and unreachable tests.
6. Confirm bounded audit events and no authentication or desktop session.
7. Revert the target snapshot and retain only redacted evidence.

## 3. Implement observation frames

1. Start only after the native certificate probe passes live verification.
2. Design a separate observation-only frame boundary.
3. Deliver redacted frames without input or redirection capabilities.
4. Enforce memory-only raw frames and bounded evidence retention.
5. Add deterministic restart, expiry, and audit coverage.

## Completion gates

- No duplicate repository or canonical document is introduced.
- Host packages are traceable to the pinned native build.
- No credentials, desktop session, raw frames, or input capability enter the
  certificate-probe milestone.
- The isolated target is disposable and reset after verification.
- All native, controller, Flutter, and BoxBrain validation passes.
