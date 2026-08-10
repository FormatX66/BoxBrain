# Change Log

## Changed state

- Replaced only the Pi trust entry for target `10.12.194.4` after exact operator
  fingerprint confirmation.
- Preserved a timestamped pre-rotation trust-file backup.
- Opened a visible restricted PowerShell-over-SSH terminal through the Pi.
- Added this session bundle and admin indexes.

## Reason

The freshly enrolled Windows SSH server presented a legitimate but unrecognized
ED25519 host key.

## Dependencies

- BoxBrain 0.14.1, Windows OpenSSH, and the `boxbrain-link` key-only account.

## Future implications

- Target identity should eventually be keyed by a durable device identifier in
  addition to a reusable USB address.
