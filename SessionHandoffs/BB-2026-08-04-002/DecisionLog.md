# Decision Log

## BB-ADR-060

- **Date:** 2026-08-04
- **Decision:** The Kali shortcut may connect only to exactly one verified,
  connected USB `boxbrain-link` target and may not perform enrollment or trust
  changes.
- **Reason:** One-click access should be convenient without turning target
  selection, host-key acceptance, or HID injection into implicit actions.
- **Alternatives considered:** Hard-code `10.12.194.4`; open an unrestricted
  target picker; combine enrollment and connection; disable strict checking.
- **Chosen solution:** Registry-based single-target selection, USB-subnet
  validation, strict pinned SSH, and non-administrator PowerShell.
- **Impact:** Clicking the desktop icon is safe and repeatable for a verified
  target, while ambiguous or offline states remain visible failures.
