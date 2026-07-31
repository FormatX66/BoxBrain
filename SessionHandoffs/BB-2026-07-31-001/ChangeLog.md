# Change Log

## Changed files

- Added the Pi Drive sync and checksum-gated patch delivery modules.
- Added the Drive OAuth configuration helper and hardened systemd timer/service.
- Extended the Pi installer and rollback-capable upgrade path.
- Added Drive and patch CLI/control-plane operations.
- Added deterministic Drive, manifest, target, checksum, and confirmation tests.
- Added the canonical Drive transport runbook.
- Updated architecture version 1.1, shared-account provisioning language,
  roadmap, TODO, decision indexes, and session records.

## Reason

The Pi needs a durable cloud exchange for logs, diagnostic evidence, and
operator-loaded maintenance packages under the approved BoxBrain service
identity.

## Dependencies

- rclone, installed separately from a verified upstream source
- Google Drive under `boxbrainprime@gmail.com`
- systemd and the existing unprivileged `boxbrain` account
- Existing key-only SSH target enrollment for optional patch delivery

## Future implications

The Drive token becomes a managed Pi runtime secret. Patch signing, retention,
Drive-side status reporting, and any execution workflow remain separate future
decisions.
