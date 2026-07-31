# Project Updates

## BoxBrain

- **Status:** Pi Drive transport implemented locally; live enrollment pending
- **Architecture:** 1.1
- **Pi edge agent:** 0.10.0
- **Account:** `boxbrainprime@gmail.com`
- **Transport:** rclone, root-folder-scoped, five-minute systemd timer
- **Patch boundary:** checksum-verified, approval-gated delivery, no execution

## BrainConnect

- No BrainConnect controller code changed.
- Existing authorized target links provide the identity-pinned SFTP boundary
  used by BoxBrain patch staging.
- Any future patch execution remains a separate BrainConnect capability and
  policy decision.

## Related projects

- Security owns future signing, retention, and token-rotation policy.
- Automation may later own Drive receipt processing and maintenance queues.
