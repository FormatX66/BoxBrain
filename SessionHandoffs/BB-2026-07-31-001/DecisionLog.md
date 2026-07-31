# Decision Log

## BB-ADR-047

- **Date:** 2026-07-31
- **Reason:** Bruce selected one ecosystem Google identity for BoxBrain machines.
- **Alternatives considered:** One Gmail and Drive per machine; a Google
  Workspace Shared Drive; one shared service account with a device-partitioned
  folder tree.
- **Chosen solution:** Use `boxbrainprime@gmail.com` with one BoxBrain root and
  device-specific Logs, Diagnostics, patch inbox, and receipt paths.
- **Impact:** Provisioning no longer creates duplicate Google identities, while
  every device still receives a distinct storage namespace.

## BB-ADR-048

- **Date:** 2026-07-31
- **Reason:** The Pi needs unattended Google Drive transport without maintaining
  a custom API client.
- **Alternatives considered:** Custom Google Drive API code; a FUSE-mounted
  Drive; service-account-only integration; rclone.
- **Chosen solution:** Adopt MIT-licensed rclone with a configured root folder
  ID, an operator-controlled headless OAuth flow, a private writable token file,
  and non-deleting `copy` commands.
- **Impact:** BoxBrain gains maintained Linux ARM and headless OAuth support
  while keeping dependency installation, credential enrollment, and upgrades
  explicit. Evidence was taken from the authoritative
  [rclone repository](https://github.com/rclone/rclone),
  [Google Drive backend documentation](https://rclone.org/drive/), and
  [remote setup documentation](https://rclone.org/remote_setup/).

## BB-ADR-049

- **Date:** 2026-07-31
- **Reason:** A cloud patch inbox is useful but cannot safely become an automatic
  software execution channel.
- **Alternatives considered:** Automatically execute every downloaded patch;
  automatically copy verified patches to targets; separate verification,
  delivery, and execution.
- **Chosen solution:** Automatically download and checksum-stage bounded patch
  packages, require explicit authorization and `DELIVER PATCH` for SFTP target
  delivery, and perform no installation or execution.
- **Impact:** Cloud transport can support maintenance without bypassing target
  authorization, host-key pinning, target identity, or later execution policy.

## BB-ADR-050

- **Date:** 2026-07-31
- **Reason:** Live enrollment warned that rclone's shared Google Drive OAuth
  client ID is being retired during 2026.
- **Alternatives considered:** Depend indefinitely on the shared client; replace
  rclone with custom Drive API code; use the shared client for the initial proof
  and migrate to a dedicated BoxBrain OAuth client.
- **Chosen solution:** Complete the bounded initial proof with the shared client,
  then migrate the existing root-scoped transport to a dedicated BoxBrain OAuth
  client before relying on it for production continuity.
- **Impact:** The working transport remains available for immediate validation,
  while client-ID retirement is an explicit near-term dependency rather than an
  untracked outage risk.
