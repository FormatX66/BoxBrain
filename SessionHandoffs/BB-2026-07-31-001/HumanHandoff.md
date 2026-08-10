# Human Handoff

## What was accomplished

- Implemented an optional Raspberry Pi Google Drive transport for service
  health snapshots, diagnostic reports, and guarded patch packages.
- Adopted rclone as the maintained upstream transport and kept installation
  separate from the BoxBrain installer.
- Added a five-minute reboot-persistent systemd timer that uses non-deleting
  copy operations.
- Added manifest, filename, size, target-hostname, and SHA-256 validation before
  a downloaded patch becomes verified.
- Added `boxbrainctl patches` and an explicitly authorized, non-executing SFTP
  delivery command for connected target accounts.
- Updated provisioning to use the shared BoxBrain ecosystem identity
  `boxbrainprime@gmail.com` instead of creating one Google identity per machine.
- Passed all 78 controller tests, all 32 Pi edge-agent tests, Flutter analysis,
  and all 19 Flutter tests.
- Installed the official signed rclone 1.74.4 Linux ARM64 release on the live
  Pi after verifying the published archive SHA-256.
- Upgraded the live Pi from BoxBrain 0.8.0 to 0.10.0 through the private,
  rollback-capable upgrade path.
- Corrected the stale API version constant and made upgrades reject a mismatch
  between the installed VERSION file and the live health endpoint.
- Verified live health, onboarding, all three core services, and the private
  rollback archive.
- Completed browser OAuth as `boxbrainprime@gmail.com` against the exact
  operator-selected root folder and installed the config as
  `boxbrain:boxbrain` mode `0600`.
- Revoked the first OAuth token immediately after rclone printed it during a
  failed validation attempt, deleted the temporary log, then hardened the
  helper with `--no-output` and local non-secret field validation before a clean
  reauthorization.
- Enabled the reboot-persistent timer and verified remote readback while the
  low-impact historical upload advanced to 223 of 998 target reports.
- Added BoxBrain 0.11 source support for a preview-first USB keyboard bootstrap
  of the fixed Windows link helper on compatible headless consoles. It types no
  credentials and requires key-only SSH verification before success.

## Decisions made

- Use one BoxBrain Drive root under the shared service identity.
- Use rclone with a root folder ID rather than a custom Google API client or a
  mounted filesystem.
- Automate transport and verification, but require explicit approval for target
  delivery and never auto-execute Drive content.
- Treat rclone's shared Google OAuth client as temporary and migrate to a
  dedicated BoxBrain client before upstream retirement interrupts service.
- Keep keystroke bootstrap fixed-command, explicitly authorized, and separate
  from BrainConnect's WinRM/JEA workflow for truly sessionless servers.

## Current blockers

- The first historical upload is still running at one transfer at a time.
- Rclone warns that its shared Google Drive client ID is being retired during
  2026; a dedicated BoxBrain OAuth client must replace it for continuity.
- The live Pi has no reviewed `/dev/hidg0` composite-gadget configuration yet;
  source 0.11.0 is not deployed and no live keystrokes were sent.

## Immediate next step

Let the first historical upload finish, verify the final state and receipt, then
create and migrate to a dedicated BoxBrain Google OAuth client. Separately,
review the Pi's composite USB gadget before any disposable-target HID proof.

## Long-term objective

Provide every authorized BoxBrain edge device with a durable, auditable cloud
exchange that preserves evidence and moves verified maintenance packages
without turning cloud storage into an execution channel.

## Session files

- [Agent handoff](AgentHandoff.md)
- [Decision log](DecisionLog.md)
- [Change log](ChangeLog.md)
- [Project updates](ProjectUpdates.md)
- [Questions](Questions.md)
- [Ideas](Ideas.md)
- [Verification checklist](VerificationChecklist.md)
- [Execution plan](ExecutionPlan.md)
