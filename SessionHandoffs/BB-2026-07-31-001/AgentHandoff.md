# Agent Handoff

## Current Objective

Complete the first historical Drive run and replace rclone's retiring shared
Google OAuth client with a dedicated BoxBrain client.

## Tasks

1. Review and merge the local Drive transport branch after CI passes.
2. Monitor the initial low-impact historical upload to a successful final state.
3. Create and verify a dedicated BoxBrain Google OAuth client.
4. Reconnect the existing exact-root rclone remote without changing Drive data.
5. Verify the first service snapshot and diagnostics upload final state.
6. Exercise one checksum-valid non-executing patch delivery in the disposable
   target and confirm the uploaded receipt.
7. Review the Pi's current USB gadget configuration and prepare a rollback plan
   before enabling the optional HID keyboard function.
8. On an authorized disposable Windows machine with an unlocked administrator
   console, preview and run one fixed bootstrap, then require key-only SSH proof.

## Dependencies

- `FormatX66/BoxBrain`
- Kali Raspberry Pi 4 at `10.12.194.1`
- `boxbrainprime@gmail.com`
- Installed rclone 1.74.4 Linux ARM64 build
- Operator-created BoxBrain Google Drive folder ID
- Dedicated BoxBrain Google OAuth client ID and secret
- Existing key-only authorized target link
- Deliberately reviewed composite USB gadget with `/dev/hidg0` for the optional
  keystroke fallback

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
- Headless bootstrap accepts no arbitrary text or credential and cannot report
  success without the target's key-only SSH proof.
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
- Blind HID input can reach the wrong UI state. Use only a physically attached,
  authorized disposable target with a known unlocked US-layout admin console;
  do not retry an unverified run automatically.

## Estimated completion order

Publish and review the branch, finish the historical sync, migrate to the
dedicated OAuth client, verify routine timer behavior, test staging, authorize
one disposable delivery, and review receipts.
