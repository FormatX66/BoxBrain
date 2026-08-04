# Change Log

## Changed files

- Added the fixed headless Windows SSH helper and Kali desktop entry.
- Added an explicit desktop-shortcut installer.
- Added source-level security assertions and documentation.
- Added this session bundle and admin indexes.

## Reason

Provide a one-click route from the Pi desktop to the currently verified
headless Windows target.

## Dependencies

- Existing `boxbrainctl`, Python 3, OpenSSH, sudo, and an XFCE-compatible
  terminal launcher.

## Future implications

- A future dashboard action can call the same fixed helper rather than
  duplicating target-selection logic.
