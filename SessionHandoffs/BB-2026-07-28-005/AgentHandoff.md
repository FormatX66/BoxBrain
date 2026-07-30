# Agent Handoff

## Current objective

Build and verify the native `brainconnect-freerdp-probe` executable against the
implemented version 1 process protocol without authenticating or starting a
desktop session.

## Tasks

1. Select and document a reproducible FreeRDP 3.x, CMake, and compiler
   baseline for Linux/Kali and Raspberry Pi.
2. Add the native helper under the existing RDP observer plugin; do not create
   a second protocol or target-identity document.
3. Register the current FreeRDP X.509 certificate callback and collect only the
   bounded fields defined in `PROTOCOL.md`.
4. Abort the connection before credential submission, NLA completion, channel
   creation, or desktop initialization.
5. Emit exactly one version 1 JSON object on success and a non-zero exit code
   on every failure.
6. Add native unit tests plus isolated-lab exact-match, mismatch, timeout, and
   no-authentication integration evidence.
7. Package the helper separately and configure only its absolute executable
   path in the controller environment.

## Dependencies

- BrainConnect `plugins/rdp-observer/PROTOCOL.md`
- BrainConnect `docs/TARGETS.md` and `docs/SECURITY.md`
- FreeRDP 3.x development package and X.509 callback API
- CMake and a supported C compiler
- An isolated, disposable Windows RDP target with an independently known
  certificate fingerprint

## Files affected

- `BrainConnect/plugins/rdp-observer/`
- BrainConnect native build and test configuration
- BrainConnect development, security, and roadmap documentation
- BoxBrain project, decision, change, and session indexes

## Required repositories

- `https://github.com/FormatX66/BrainConnect`
- `https://github.com/FormatX66/BoxBrain`

## Verification checklist

- The helper implements protocol schema version 1 exactly.
- The configured target host, port, and expected fingerprint remain separate
  argument-array values.
- A registered disabled target can be probed before operator approval.
- Exact identity returns bounded metadata without enabling the target.
- Mismatch returns the observed fingerprint; the controller disables an
  enabled target and appends `target.identity_mismatch`.
- No credentials, NLA completion, desktop session, input, clipboard, file,
  shell, audio, print, drive, or device-redirection path exists.
- Certificate-ignore, trust-on-first-use, known-host acceptance, and fallback
  behavior are absent.
- Native, controller, Flutter, and BoxBrain validation passes.

## Suggested commit message

`feat: build native FreeRDP certificate helper`

## Suggested branch

`feature/brainconnect-freerdp-native-probe`

## Potential risks

- A FreeRDP callback may run after more of the authentication state machine
  than expected; prove the abort point with test evidence.
- FreeRDP callback names and ownership rules differ across versions; pin and
  document the supported baseline.
- Generic FreeRDP client defaults could silently enable channels or credential
  prompts.
- Returning a zero exit code on mismatch could be confused with trusted
  identity unless the JSON and controller comparison remain authoritative.
- The older session 004 statement that disabled targets cannot be probed is
  superseded: pre-approval certificate probing is required by the canonical
  target workflow.

## Estimated completion order

1. Reproducible toolchain
2. Minimal native executable and argument parser
3. X.509 callback and pre-authentication abort
4. Version 1 JSON serialization
5. Native unit tests
6. Isolated-lab integration tests
7. Packaging and controller configuration
8. Documentation and BoxBrain handoff
