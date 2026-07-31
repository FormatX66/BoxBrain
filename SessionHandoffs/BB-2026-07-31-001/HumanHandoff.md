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
- Confirmed read-only that rclone is not currently installed on the live Pi.

## Decisions made

- Use one BoxBrain Drive root under the shared service identity.
- Use rclone with a root folder ID rather than a custom Google API client or a
  mounted filesystem.
- Automate transport and verification, but require explicit approval for target
  delivery and never auto-execute Drive content.

## Current blockers

- Installing rclone on the live Pi requires explicit operator approval and a
  verified ARM release or approved package source.
- The `BoxBrain` folder must be created while signed into
  `boxbrainprime@gmail.com`, and its folder ID is required.
- The one-time browser OAuth flow must be completed by the operator; the current
  Codex Drive connector is still authenticated as `arkmatx@gmail.com`.

## Immediate next step

Approve a verified rclone installation on the Pi, create the BoxBrain Drive
folder under `boxbrainprime@gmail.com`, and run the guarded one-time enrollment.

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
