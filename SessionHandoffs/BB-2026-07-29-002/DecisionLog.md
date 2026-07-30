# Decision Log

## BB-ADR-016

- **Date:** 2026-07-29
- **Reason:** Windows Sandbox could not expose the distinct RDP listener needed
  for certificate and later frame-transport work.
- **Alternatives considered:** Windows Sandbox, the personal workstation, a
  dedicated physical computer, or a full Hyper-V VM.
- **Chosen solution:** Use a disposable Generation 2 Hyper-V Windows VM with
  Secure Boot, virtual TPM, a dedicated VHD, and an external switch bound only
  to the Raspberry Pi USB adapter. Apply verified Windows media directly to
  the blank VHD when the UEFI boot-key path is unreliable.
- **Impact:** The lab now has a separate, resettable Windows identity and RDP
  listener without placing personal accounts, files, or broad networking in
  the target.

## BB-ADR-017

- **Date:** 2026-07-29
- **Reason:** The Pi needs a narrow way to confirm and diagnose the target
  without copying its controller token or granting an administrator account.
- **Alternatives considered:** RDP credentials, WinRM, a broad administrator
  SSH account, a host dashboard token, or a restricted target account.
- **Chosen solution:** Keep RDP for the future certificate/frame boundary and
  provision a separate `boxbrain-link` non-administrator account using one
  injected Pi public key, public-key-only SSH, no TTY or forwarding, and a
  firewall remote address of exactly `10.12.194.1`.
- **Impact:** The Pi can discover and run reviewed read-only diagnostics while
  the workstation and other network peers cannot use the SSH listener.

## BB-ADR-018

- **Date:** 2026-07-29
- **Reason:** `Get-PnpDevice` on a freshly serviced 1 GiB Windows VM exceeded
  the Pi diagnostic's 90-second outer deadline.
- **Alternatives considered:** Increase the outer timeout, remove device
  inventory, run the scan unbounded, or bound only the slow sub-check.
- **Chosen solution:** Run device inventory in a job with a 15-second deadline,
  stop and remove that job on timeout, and return
  `device_error_check = timed-out` with an empty bounded result.
- **Impact:** The full read-only diagnostic completes predictably while
  preserving explicit evidence that device-error coverage was incomplete.
