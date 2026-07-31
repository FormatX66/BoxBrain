# Project Updates

## BoxBrain

- **Status:** Pi Drive transport deployed and enrolled; historical sync running
- **Architecture:** 1.1
- **Pi edge agent source:** 0.11.0
- **Account:** `boxbrainprime@gmail.com`
- **Transport:** rclone, root-folder-scoped, five-minute systemd timer
- **Patch boundary:** checksum-verified, approval-gated delivery, no execution
- **Live Pi:** BoxBrain 0.10.0, rclone 1.74.4, core services healthy, Drive
  timer enabled, private OAuth config installed, remote readback proven
- **Headless fallback:** fixed USB-HID Windows link implemented preview-first;
  live HID gadget configuration and disposable-target proof remain pending
- **Continuity:** Dedicated BoxBrain OAuth client required before rclone's
  shared client ID retires

## BrainConnect

- No BrainConnect controller code changed; managed sessionless-server repair
  remains in BrainConnect's separate WinRM HTTPS/JEA workflow.
- Existing authorized target links provide the identity-pinned SFTP boundary
  used by BoxBrain patch staging.
- Any future patch execution remains a separate BrainConnect capability and
  policy decision.

## Related projects

- Security owns future signing, retention, and token-rotation policy.
- Automation may later own Drive receipt processing and maintenance queues.
