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
  rollback archive. The Drive timer remains disabled and no OAuth file exists.

## Decisions made

- Use one BoxBrain Drive root under the shared service identity.
- Use rclone with a root folder ID rather than a custom Google API client or a
  mounted filesystem.
- Automate transport and verification, but require explicit approval for target
  delivery and never auto-execute Drive content.

## Current blockers

- The `BoxBrain` folder must be created while signed into
  `boxbrainprime@gmail.com`, and its folder ID is required.
- The one-time browser OAuth flow must be completed by the operator; the current
  Codex Drive connector is still authenticated as `arkmatx@gmail.com`.

## Immediate next step

Provide the BoxBrain Drive folder URL or ID, then complete the guarded one-time
OAuth enrollment while selecting `boxbrainprime@gmail.com`.

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
