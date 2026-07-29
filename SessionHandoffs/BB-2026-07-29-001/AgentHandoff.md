# Agent Handoff

## Current objective

Move from the proven Pi certificate-identity boundary to observation-only
frames from one explicitly authorized disposable desktop target.

## Tasks

1. Select a full Windows VM or dedicated lab machine that is operator-owned,
   disposable, isolated, and snapshotted.
2. Record its endpoint and certificate fingerprint through a path independent
   of BrainConnect.
3. Define a bounded frame protocol with dimensions, cadence, size, redaction,
   retention, and backpressure limits.
4. Keep certificate verification mandatory before any frame connection.
5. Decide how the dashboard obtains a controlled controller session without
   embedding the Pi bearer token.
6. Verify no credential, authentication callback, keyboard, pointer,
   clipboard, file, device, or shell action occurs.
7. Add deterministic protocol, failure, and redaction tests before a live run.
8. Restore the disposable target snapshot and retain only approved evidence.

## Dependencies

- BrainConnect branch `feature/brainconnect-pi-rdp-live-lab` at `1df9de7`
- Draft BrainConnect pull request
  [7](https://github.com/FormatX66/BrainConnect/pull/7)
- Deployed controller revision
  `1df9de72805c01f1a10908424096d1fcaf0bda40`
- Controller wheel SHA-256
  `3de9fcb43861f8fa6517b20a148680704228ca63b657dc6bc04c6f9cf25a0e3e`
- Installed helper SHA-256
  `b2108177d6b0d1fd126b16b96b186ea40aead6acc4cd6a6ffeb5815851def6a1`
- Enabled USB-bound controller at `10.12.194.1:8000`
- A disposable full desktop target

## Files affected

- BrainConnect observation plugin, frame protocol, tests, security, target, and
  roadmap documentation
- BrainConnect Flutter observation view after the protocol is proven
- BoxBrain project, decision, change, roadmap, and session indexes
- Pi SQLite target and audit state through authenticated controller operations

## Required repositories

- `https://github.com/FormatX66/BrainConnect`
- `https://github.com/FormatX66/BoxBrain`

## Verification checklist

- Controller remains enabled, active, authenticated, and USB-only.
- Deployed controller and helper hashes match provenance.
- Target starts disabled and the exact certificate gate passes independently.
- Frames are bounded, redacted, non-persistent by default, and backpressured.
- Certificate mismatch disables the target before further observations.
- Timeout and disconnect paths are bounded and audited.
- No token, credential, private key, or raw frame enters Git or logs.
- No authentication, input, shell, clipboard, file, or device redirection runs.
- Target snapshot restoration is confirmed.
- BrainConnect and BoxBrain validation passes.

## Suggested commit message

`feat: add bounded RDP frame observation`

## Suggested branch

`feature/brainconnect-rdp-frame-observer`

## Potential risks

- A full desktop target can contain personal data if isolation is incomplete.
- Frame evidence can expose sensitive screen content even without input.
- Certificate rotation can interrupt observations and must remain fail-closed.
- Browser delivery can broaden token exposure if credential provisioning is
  not separated from the web build.
- Adding a desktop library can accidentally enable authentication or device
  redirection unless the boundary is independently reviewed.

## Estimated completion order

1. Target ownership, isolation, and snapshot
2. Independent endpoint and certificate identity
3. Frame protocol and evidence policy
4. Deterministic fixture and failure tests
5. Native observation implementation
6. Controlled live verification
7. Flutter display and credential-session decision
8. Documentation, review, and next handoff
