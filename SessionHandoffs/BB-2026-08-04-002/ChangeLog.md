# Change Log

## Changed files

- Added the fixed headless Windows SSH helper and Kali desktop entry.
- Added an explicit desktop-shortcut installer.
- Added source-level security assertions and documentation.
- Added this session bundle and admin indexes.
- Installed the committed helper as root-owned mode `0755` and the desktop
  entry as `kali`-owned mode `0755` on the Pi.
- Click-verified the launcher against connected target `DESKTOP-3U8PBEN` at
  `10.12.194.4` using the restricted `boxbrain-link` account.

## Reason

Provide a one-click route from the Pi desktop to the currently verified
headless Windows target.

## Dependencies

- Existing `boxbrainctl`, Python 3, OpenSSH, sudo, and an XFCE-compatible
  terminal launcher.

## Future implications

- A future dashboard action can call the same fixed helper rather than
  duplicating target-selection logic.
