# Agent Handoff

## Current objective

Verify the deployed Pi controller and native helper against one explicitly
authorized, disposable Windows RDP target without authenticating or opening a
desktop session.

## Tasks

1. Confirm the Windows target is disposable, isolated, operator-owned, and
   snapshotted.
2. Record its exact hostname or IP, RDP port, and SHA-256 certificate
   fingerprint through a separate trusted path.
3. Decide how the local dashboard obtains a short-lived or otherwise controlled
   controller credential without committing or broadly copying the Pi token.
4. Register the target disabled and confirm its durable audit record.
5. Probe an exact certificate match and confirm `last_verified_at`.
6. Exercise changed-certificate, unreachable, and bounded-timeout cases.
7. Confirm every failure is bounded and audited and that a mismatch disables an
   enabled target atomically.
8. Confirm no credential, authentication callback, desktop session, frame,
   clipboard, file, device, keyboard, pointer, or shell action occurs.
9. Restore the target snapshot and retain only approved redacted evidence.

## Dependencies

- BrainConnect branch `feature/brainconnect-pi4-controller` at `ee9c518`
- Deployed controller release
  `016ec1f5b20db4c4b9679da74f8e36be4e1a11aa`
- Enabled `brainconnect-controller.service` on `10.12.194.1:8000`
- Installed helper SHA-256
  `b2108177d6b0d1fd126b16b96b186ea40aead6acc4cd6a6ffeb5815851def6a1`
- BrainConnect target registry, emergency stop, and certificate-only probe
  contracts
- An explicitly authorized disposable Windows target

## Files affected

- BrainConnect live-lab integration tests and redacted evidence definitions
- BrainConnect target, security, development, and roadmap documentation
- BoxBrain project, decision, change, roadmap, and session indexes
- Pi SQLite state through authenticated target and audit API operations

## Required repositories

- `https://github.com/FormatX66/BrainConnect`
- `https://github.com/FormatX66/BoxBrain`

## Verification checklist

- Controller remains enabled and active after a fresh Pi restart.
- API still listens only on `10.12.194.1:8000`.
- Unauthenticated health remains HTTP 401.
- Token and database remain mode `0600` in a mode `0700` directory.
- Installed controller and helper hashes still match provenance.
- Target begins disabled and cannot admit tasks before explicit enablement.
- Exact match updates verification time without authentication.
- Mismatch disables the target and appends the bounded audit event atomically.
- Timeout and unreachable results remain bounded and omit untrusted stderr.
- No credential, desktop session, frame, input, shell, clipboard, file, or
  device redirection is exercised.
- BrainConnect and BoxBrain validation passes.

## Suggested commit message

`test: verify isolated Windows RDP certificate boundary`

## Suggested branch

`feature/brainconnect-windows-rdp-live-lab`

## Potential risks

- A Windows update or RDP configuration change can rotate the certificate.
- Testing the wrong network endpoint could contact a non-lab system.
- Copying the long-lived Pi token to a browser build would broaden credential
  exposure.
- Restarting networking can reset the direct USB route.
- Any attempt to supply RDP credentials would exceed this milestone.

## Estimated completion order

1. Target authorization, isolation, and snapshot
2. Independent endpoint and fingerprint verification
3. Controlled controller-session credential decision
4. Disabled target registration
5. Exact-match probe
6. Mismatch, timeout, and unreachable probes
7. Audit and no-authentication verification
8. Snapshot restore, documentation, review, and BoxBrain handoff
