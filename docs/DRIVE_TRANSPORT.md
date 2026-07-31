# Raspberry Pi Google Drive Transport

BoxBrain can use one operator-owned Google Drive folder as a reboot-persistent
exchange point for Pi service telemetry, diagnostic reports, and staged patch
packages. The current ecosystem account is `boxbrainprime@gmail.com`.

The transport uses [rclone](https://rclone.org/drive/) rather than a custom
Google Drive client. Rclone is MIT-licensed, actively released, supports Linux
ARM builds and headless OAuth, and provides non-deleting `copy` operations.
BoxBrain does not install rclone automatically and does not commit its OAuth
token.

## Drive layout

Create one top-level `BoxBrain` folder in the service account. The rclone remote
must use that folder's ID as `root_folder_id`, limiting the transport to this
tree:

```text
BoxBrain/
  Logs/<device-id>/
  Config/
  Projects/
  Repositories/
    Patches/
      inbox/<device-id>/
      receipts/<device-id>/
  Backups/
  Media/
  Diagnostics/<device-id>/
```

The timer uploads service health snapshots and diagnostic reports with
`rclone copy`; it never mirrors deletions. It downloads patch candidates from
the device inbox, rejects path traversal, non-allowlisted package types,
oversized payloads, malformed manifests, target mismatches, and failed SHA-256
checks, then stores accepted content under a content-addressed local reference.

## One-time Pi enrollment

The initial OAuth step requires the operator because Google authentication and
account selection must remain user-controlled. Rclone cannot independently
prove the Gmail address for the Google Drive backend, so the helper displays the
expected address and requires an exact account attestation after OAuth.

Prerequisites:

- a verified rclone installation available as `/usr/bin/rclone`;
- the `BoxBrain` Drive folder ID from the browser URL;
- the intended Pi device ID, such as `kali-pi-usbc`;
- browser access to `boxbrainprime@gmail.com` on an operator-controlled device.

After installing or upgrading the edge agent, run:

```bash
sudo boxbrain-drive-configure \
  kali-pi-usbc \
  <BOXBRAIN_DRIVE_FOLDER_ID> \
  boxbrainprime@gmail.com
```

The helper creates a remote named `boxbrain-drive` with provider `drive`, scope
`drive`, and the exact root folder ID. On a headless Pi, forward rclone's local
OAuth callback over the verified SSH connection and finish authorization on
the operator device.
The full Drive scope is required because patches placed through the Drive web
interface are not necessarily visible through the narrower `drive.file` scope;
the configured root folder ID provides the storage boundary.

The helper suppresses rclone's credential-bearing configuration output,
validates only the local remote type, scope, and root ID, verifies root access,
and installs the token in the private BoxBrain identity directory as
`boxbrain:boxbrain` mode `0600`. It creates missing
standard folders without deleting existing content, enables the five-minute
systemd timer, and runs the first sync. No password enters BoxBrain or Git.

Verify:

```bash
systemctl status boxbrain-drive-sync.timer
systemctl status boxbrain-drive-sync.service
boxbrainctl patches
```

## Patch manifest

Upload a payload and a same-ID JSON manifest directly into
`Repositories/Patches/inbox/<device-id>`. Example:

```json
{
  "schema_version": 1,
  "patch_id": "windows-kb-example",
  "target_hostname": "HEX-LAPTOP",
  "payload": "windows-kb-example.msu",
  "sha256": "<64-lowercase-hex-digits>",
  "size_bytes": 123456
}
```

The manifest file must be named `<patch_id>.json`. Patch download and checksum
verification are automatic. Delivery is deliberately separate:

```bash
boxbrainctl patches
boxbrainctl deliver-patch <verified-reference> \
  --authorized \
  --confirmation "DELIVER PATCH"
```

Delivery rechecks the checksum, resolves `target_hostname` to exactly one
connected authorized link, requires a pinned SSH host key, and uses SFTP to
place the payload and manifest under the restricted account's
`BoxBrain/Patches/incoming` directory. It writes a receipt for the next Drive
upload. It does not launch, install, or execute the patch.

## Security and recovery

- Drive sync is disabled until the one-time helper succeeds.
- The timer runs as the existing unprivileged `boxbrain` service account.
- The OAuth configuration is excluded from Git and protected by filesystem
  permissions.
- Google Drive shortcuts are ignored.
- Cloud deletion does not delete Pi evidence, and Pi deletion does not delete
  Drive evidence.
- A patch cannot select an arbitrary target path or execution command.
- Revoking OAuth access or disabling the timer is a separate operator action.

If the wrong Google account is selected, stop without installing the token and
repeat the enrollment with the correct browser identity.
