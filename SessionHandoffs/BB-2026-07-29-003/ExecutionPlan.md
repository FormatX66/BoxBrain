# Execution Plan

## 1. Completed full Windows certificate gate

1. [x] Confirm the clean Windows target is running.
2. [x] Confirm RDP reachable and workstation SSH blocked.
3. [x] Read the RDP certificate independently from the guest store.
4. [x] Register the exact target disabled by default.
5. [x] Probe through the Pi helper without credentials.
6. [x] Confirm certificate, host, port, subject, and issuer.
7. [x] Confirm no authentication or desktop session.
8. [x] Verify registration and identity audit events.
9. [x] Enable only after the exact independent match.
10. [x] Revoke and rotate the controller token exposed during diagnostics.
11. [x] Verify replacement-token ownership, authentication, and service health.

## 2. Next observation-only frame contract

1. Define schema version, dimensions, pixel format, sequence, and timestamp.
2. Set hard per-frame and total-memory limits.
3. Set cadence, queue, timeout, retry, and backpressure limits.
4. Use a deterministic fixture before a Windows session.
5. Reject malformed, oversized, stale, and identity-mismatched frames.
6. Apply redaction before delivery.
7. Retain no raw frames by default.
8. Keep every input and redirection capability unavailable.

## 3. Controlled live observation

1. Approve a separate external low-privilege credential provider.
2. Reconfirm certificate identity.
3. Start one bounded observation-only session.
4. Prove no input or redirection capability.
5. Stop the session and clear memory-only frames.
6. Restore checkpoint `clean-linked-2026-07-29`.
7. Reverify endpoint and certificate before re-enablement.

## Completion gates

- Certificate identity remains independently reproducible.
- No credential enters Git, SQLite, Flutter assets, arguments, or audit data.
- Frame memory and cadence are hard-bounded.
- Redaction precedes any delivery or persistence.
- All error paths are bounded and audited.
- No keyboard, pointer, clipboard, file, device, audio, or shell action exists.
- BrainConnect and BoxBrain validation passes.
