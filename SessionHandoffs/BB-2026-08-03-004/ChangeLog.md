# Change Log

## Changed files

- Added access-point runtime, configurator, systemd units, rollback timer, CLI,
  deterministic tests, installer support, and upgrade rollback coverage.
- Updated edge-agent version, architecture, operator documentation, roadmap,
  indexes, and this session bundle.

## Reason

Provide a persistent recovery link before enabling the Pi's composite USB
Ethernet, keyboard, and mouse functions.

## Dependencies

NetworkManager, `iw`, nftables, the Pi Wi-Fi AP/managed combination, ConfigFS,
RNDIS, and USB HID gadget functions.

## Future implications

The dashboard can expose AP state without storing its key. A second Wi-Fi radio
may later remove same-channel coupling. HID actions remain separately gated.
