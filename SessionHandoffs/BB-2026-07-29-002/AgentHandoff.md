# Agent Handoff

## Current objective

Promote the clean Hyper-V Windows target into BrainConnect's existing
certificate-pinned target registry, then add bounded observation-only frames
without enabling input or broad credentials.

## Tasks

1. Confirm checkpoint `clean-linked-2026-07-29` and start
   `BoxBrain-Windows-Lab`.
2. Confirm the guest retains Pi-only address `10.12.194.9`, RDP port 3389, and
   restricted SSH status from the Pi.
3. Obtain the RDP certificate fingerprint through a path independent of the
   BrainConnect stored target record.
4. Register the RDP endpoint disabled by default and run the existing native
   helper probe without credentials.
5. Enable only after exact certificate confirmation and audit verification.
6. Specify frame dimensions, cadence, size, redaction, retention,
   backpressure, and disconnect behavior.
7. Keep authentication, keyboard, pointer, clipboard, file, device, audio,
   shell, and drive redirection unavailable.
8. Restore the clean checkpoint after each live observation experiment.

## Dependencies

- Hyper-V VM `BoxBrain-Windows-Lab`
- Standard checkpoint `clean-linked-2026-07-29`
- Guest endpoint `10.12.194.9:3389` on switch `BoxBrain-Pi-USB`
- Pi endpoint `10.12.194.1`
- Verified guest status:
  `C:\VMs\BoxBrain-Windows-Lab\guest-verification.json`
- Verified checkpoint status:
  `C:\VMs\BoxBrain-Windows-Lab\checkpoint-status.json`
- Pi read-only diagnostic generated
  `2026-07-29T15:23:14.451472+00:00`
- BrainConnect revision `746dfdc` on
  `feature/brainconnect-pi-rdp-live-lab`
- BrainConnect draft pull request
  [7](https://github.com/FormatX66/BrainConnect/pull/7)

## Files affected

- `sandbox/hyperv/`
- `edge/kali-pi-agent/onboarding/windows-link.ps1`
- `edge/kali-pi-agent/src/boxbrain/diagnostics.py`
- `edge/kali-pi-agent/tests/test_core.py`
- `controller/pyproject.toml`
- `Admin/validate_repository.py`
- `Admin/tests/test_validate_repository.py`
- `README.md`
- `Admin/`
- `Architecture/`
- `Projects/BrainConnect/ProjectIndex.md`
- `SessionHandoffs/BB-2026-07-29-002/`

## Required repositories

- `https://github.com/FormatX66/BoxBrain`
- `https://github.com/FormatX66/BrainConnect`

## Verification checklist

- VM starts only from the clean checkpointed baseline.
- VM address and RDP endpoint are independently reconfirmed.
- Pi-only SSH firewall still contains exactly `10.12.194.1`.
- Restricted link user remains outside Administrators.
- BrainConnect target begins disabled.
- Native probe uses no credential and matches the independently recorded
  certificate.
- Every mismatch, timeout, disconnect, and disable action is audited.
- No raw frame, credential, private key, token, or lab password enters Git.
- Frame evidence is bounded, redacted, and non-persistent by default.
- Checkpoint restoration is verified after the run.
- BrainConnect and BoxBrain validation passes.

## Suggested commit message

`feat: add clean Hyper-V Windows target`

## Suggested branch

Continue `codex/repository-organization` for the BoxBrain handoff; use
`feature/brainconnect-rdp-frame-observer` for new BrainConnect implementation.

## Potential risks

- Low host memory can make guest servicing and diagnostics slow.
- RDP authentication can accidentally broaden the current certificate-only
  boundary.
- Frame capture can disclose guest screen content even when input is disabled.
- Restoring a checkpoint can rotate network or RDP identity if not verified.
- The detached answer ISO contains a one-time plaintext lab password.
- Future Pi onboarding changes alter the served script hash because the public
  key is injected at install time.

## Estimated completion order

1. Baseline start and endpoint confirmation
2. Independent RDP certificate identity
3. Disabled target registration and probe
4. Exact-match enablement proof
5. Frame protocol and evidence policy
6. Deterministic fixtures and failure tests
7. Controlled live frame observation
8. Checkpoint restoration and documentation
