# Human Handoff

## What was accomplished

- Verified the official Windows 11 Enterprise Evaluation 25H2 ISO against
  Microsoft's published SHA-256.
- Created `BoxBrain-Windows-Lab`, a Generation 2 Hyper-V VM with Secure Boot,
  virtual TPM, a 64 GiB dynamic disk, dynamic memory, and a network switch
  bound only to the Raspberry Pi USB adapter.
- Applied Windows directly to the exact blank VHD after the UEFI boot-key path
  proved unreliable.
- Verified the guest as `BB-WIN-LAB`, Windows 11 Enterprise Evaluation 25H2,
  with Hyper-V heartbeat OK and Pi-only address `10.12.194.9`.
- Enabled RDP and proved it reachable at `10.12.194.9:3389`.
- Fixed the Pi Windows onboarding script's single-address strict-mode bug,
  tested it, deployed it with a rollback copy, and hash-verified the served
  result.
- Provisioned the `boxbrain-link` account and proved it is enabled,
  non-administrator, public-key-only, and limited by firewall to Pi address
  `10.12.194.1`.
- Bounded the Windows device inventory to 15 seconds so a slow `Get-PnpDevice`
  call cannot consume the Pi diagnostic's full 90-second deadline.
- Deployed that diagnostic fix and completed a Pi-originated read-only report:
  healthy, no findings, 64.3% disk free, no pending reboot, and no Wi-Fi
  credential exposure.
- Replaced the deprecated TestClient development transport with `httpx2`
  2.9.x; all 57 backend tests now pass without the upstream migration warning.
- Corrected the repository validator so ignored local environments cannot
  create false orphan-document or broken-link failures.
- Gracefully shut down the VM and created Standard checkpoint
  `clean-linked-2026-07-29`.

## Decisions made

- Use a dedicated Generation 2 Hyper-V VM, not Windows Sandbox or the
  workstation, as the disposable full Windows target.
- Keep target access split: RDP for the future observation boundary and a
  restricted Pi-only SSH account for audited read-only system intelligence.
- Give potentially slow device discovery its own deadline and report the
  incomplete check instead of hiding or extending it.

## Current blockers

- BrainConnect has not registered `10.12.194.9:3389` or independently recorded
  its RDP certificate fingerprint.
- Observation frames, credential/session provisioning, redaction, and
  backpressure remain unimplemented.
- The VM uses a 1 GiB startup/minimum allocation because the workstation could
  not reserve 2 GiB; post-install servicing is slower under current host
  memory pressure.
- The detached answer ISO still contains the one-time lab password. Removing
  it requires a separate explicit cleanup request after recovery needs are
  reviewed.
- BoxBrain pull request 3 still requires review and merge.

## Immediate next step

Restore or start the clean checkpoint, register the disabled RDP target in
BrainConnect, independently record its certificate fingerprint, and prove the
existing certificate gate before any credential or frame work begins.

## Long-term objective

Operate a resettable, Pi-connected Windows research target that BrainConnect
can observe through a bounded, certificate-pinned, redacted, no-input frame
transport with auditable restoration between experiments.
