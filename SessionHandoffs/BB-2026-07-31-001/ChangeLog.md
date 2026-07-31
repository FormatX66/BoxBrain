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
- Corrected the edge-agent API version to 0.10.0 and made upgrade verification
  fail closed when live health reports a different version.
- Installed verified rclone 1.74.4 and deployed BoxBrain 0.10.0 to the live Pi
  before the separate operator-controlled OAuth enrollment.
- Automated exact remote creation, suppressed credential-bearing rclone output,
  and replaced redacted-output validation with local non-secret field checks.
- Revoked an initially exposed OAuth token, removed its temporary log, and
  completed a clean replacement authorization with zero sensitive log lines.
- Enabled the live timer, proved remote readback, and extended the bounded
  single-transfer window for the initial 998-file historical backlog.

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
