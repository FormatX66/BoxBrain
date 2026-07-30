# Agent Handoff

## Current objective

Build BrainConnect's out-of-process, certificate-only FreeRDP observation
probe against the approved target registry.

## Tasks

1. Define a fixed allowlist of FreeRDP executable arguments and environment.
2. Add a subprocess adapter that probes the RDP server certificate without
   authenticating to a desktop.
3. Compare the observed SHA-256 fingerprint with the enabled target record.
4. Reject and disable the target on mismatch, with an append-only audit event.
5. Add deterministic fake-process, timeout, mismatch, and migration-safe tests.
6. Document the process boundary before adding any frame observation.

## Dependencies

- BrainConnect `docs/TARGETS.md`
- BrainConnect target database and authenticated controller API
- FreeRDP 3.x availability for integration testing
- Existing policy, audit, and emergency-stop services

## Files affected

- `BrainConnect/controller/src/brainconnect_controller/`
- `BrainConnect/controller/tests/`
- BrainConnect architecture, security, roadmap, and target documentation
- BoxBrain project, decision, change, and handoff indexes

## Required repositories

- `https://github.com/FormatX66/BrainConnect`
- `https://github.com/FormatX66/BoxBrain`

## Verification checklist

- FreeRDP runs out of process with fixed arguments.
- The probe does not submit credentials or establish a desktop session.
- Exact certificate matches succeed for enabled targets.
- Mismatches reject the probe, disable the target, and create an audit event.
- Disabled and missing targets cannot be probed.
- Timeout and process-failure paths are deterministic and audited.
- No keyboard, pointer, clipboard, file, shell, audio, print, drive, or device
  redirection capability is enabled.
- Controller tests pass with zero warnings.
- BoxBrain structural and link validation passes.

## Suggested commit message

`feat: add certificate-pinned RDP observation probe`

## Suggested branch

`feature/brainconnect-rdp-observer`

## Potential risks

- Accidentally authenticating while attempting to inspect the certificate.
- Accepting a host name or endpoint match in place of an exact certificate
  match.
- Passing user-controlled values as arbitrary FreeRDP command-line arguments.
- Failing to disable a previously approved target after identity changes.
- Expanding the probe into keyboard, pointer, shell, file, or device access.

## Estimated completion order

1. Process contract and fixed arguments
2. Certificate-probe adapter
3. Registry comparison and mismatch disable
4. Audit events and error mapping
5. Unit and integration tests
6. Security and roadmap documentation
7. BoxBrain handoff update
