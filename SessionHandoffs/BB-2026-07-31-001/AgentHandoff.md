# Agent Handoff

## Current Objective

Deploy and enroll the reviewed Pi Drive transport only after explicit approval
for the missing dependency and operator-controlled Google OAuth.

## Tasks

1. Review and merge the local Drive transport branch after CI passes.
2. Select and verify the exact rclone ARM installation artifact or package.
3. Create the BoxBrain root folder in the intended Google account.
4. Upgrade the Pi edge agent through its rollback-capable installer.
5. Run `boxbrain-drive-configure` with the root folder ID.
6. Verify the first service snapshot and diagnostics upload.
7. Exercise one checksum-valid non-executing patch delivery in the disposable
   target and confirm the uploaded receipt.

## Dependencies

- `FormatX66/BoxBrain`
- Kali Raspberry Pi 4 at `10.12.194.1`
- `boxbrainprime@gmail.com`
- Verified rclone Linux ARM build
- Operator-created BoxBrain Google Drive folder ID
- Existing key-only authorized target link

## Files affected

- Pi Drive sync and patch modules under `edge/kali-pi-agent/src/boxbrain`
- Pi installer, upgrade, configuration helper, systemd service, and timer
- Controller provisioning language and architecture version
- Drive transport runbook, roadmap, TODO, tests, and session indexes

## Required repositories

- `FormatX66/BoxBrain`

## Verification checklist

- All controller and Pi tests pass.
- POSIX deployment scripts parse with LF endings.
- No OAuth token, password, private key, or target credential is committed.
- Drive timer is not enabled before successful OAuth enrollment.
- The rclone remote uses the exact BoxBrain root folder ID.
- Uploads use `copy`, not deletion-mirroring `sync`.
- Invalid or mismatched patch manifests remain unverified.
- Delivery requires authorization, exact confirmation, pinned host key, and a
  unique connected hostname.
- Delivered content remains unexecuted in the restricted target account.

## Suggested commit message

`Add guarded Pi Google Drive transport`

## Suggested branch

`codex/pi-drive-sync`

## Potential risks

- Google Drive scope `drive` can access more than the configured root if the
  token or configuration is misused; the dedicated ecosystem account and Pi
  filesystem boundary reduce but do not eliminate this risk.
- OAuth tokens must remain writable by rclone so refreshes persist.
- Cloud content is untrusted even when it belongs to the service account.
- Patch delivery writes to a target and must stay approval-gated and separate
  from installation or execution.

## Estimated completion order

Merge code, approve dependency, verify artifact, upgrade Pi, create Drive root,
complete OAuth, verify timer, test staging, authorize one disposable delivery,
and review receipts.
