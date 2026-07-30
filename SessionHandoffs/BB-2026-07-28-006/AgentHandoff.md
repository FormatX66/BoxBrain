# Agent Handoff

## Current objective

Package and live-verify `brainconnect-freerdp-probe` on a Linux/Pi controller
against an isolated disposable Windows RDP target without submitting
credentials or starting a desktop session.

## Tasks

1. Choose the isolated Windows VM and independently record its RDP endpoint
   and SHA-256 server-certificate fingerprint.
2. Produce a Linux amd64 and/or arm64 package from the existing pinned build;
   do not invent a second helper protocol.
3. Record package provenance, runtime dependencies, and SHA-256 checksums.
4. Install only on the isolated controller and configure the helper's absolute
   executable path.
5. Verify exact fingerprint, changed fingerprint, timeout, and unreachable
   endpoint behavior through the controller API.
6. Prove no credentials, NLA completion, `PostConnect`, channels, frame data,
   input, or redirection are reached.
7. Revert the disposable target snapshot and preserve only bounded audit
   evidence.

## Dependencies

- BrainConnect native helper and version 1 process protocol
- Debian 13 / FreeRDP 3.15.x runtime for the selected controller architecture
- Isolated disposable Windows VM with RDP enabled
- Independently obtained RDP certificate fingerprint
- Existing BrainConnect target registry, emergency stop, and audit store

## Files affected

- BrainConnect native packaging and installation scripts
- BrainConnect development, deployment, security, and roadmap documentation
- BrainConnect isolated-lab tests or evidence manifest
- BoxBrain project, decision, change, and session indexes

## Required repositories

- `https://github.com/FormatX66/BrainConnect`
- `https://github.com/FormatX66/BoxBrain`

## Verification checklist

- Package checksum and source revision are recorded.
- The installed binary reports FreeRDP 3.15.x.
- The executable path is operator configuration, not API input.
- Exact identity updates verification time without enabling the target.
- Changed identity disables an enabled target atomically.
- TLS-only selection, timeout, unreachable endpoint, and malformed data fail
  closed with bounded audit codes.
- No credential, desktop session, channel, frame, input, shell, file, or
  device-redirection path is reached.
- The target snapshot is reverted after the run.
- Native, controller, Flutter, and BoxBrain validation passes.

## Suggested commit message

`test: verify native RDP probe against isolated Windows target`

## Suggested branch

`feature/brainconnect-rdp-live-lab`

## Potential risks

- Windows can rotate its RDP certificate, so the expected fingerprint must be
  obtained independently for each controlled fixture.
- A host package can accidentally drift from the pinned Docker build; checksum
  and version evidence must bind it to the source revision.
- FreeRDP configuration changes can re-enable fallback protocols or channels.
- Live-lab evidence can leak hostnames, usernames, certificates, or screen
  content if it is not bounded and redacted.
- The pull-request chain must remain ordered while branches are stacked.

## Estimated completion order

1. Select and snapshot isolated target
2. Build package and provenance record
3. Install on controller host
4. Exact-match live test
5. Changed-certificate and failure tests
6. Audit and no-authentication review
7. Documentation and BoxBrain handoff
8. Commit, push, and stacked draft review
