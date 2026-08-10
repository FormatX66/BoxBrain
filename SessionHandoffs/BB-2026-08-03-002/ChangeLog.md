# Change Log

## Changed files

- Added the canonical connection lifecycle architecture.
- Added edge-agent connection inventory and local HTML table.
- Added bounded controller models and sanitization for connection-map payloads.
- Added Flutter models and a connection-map dashboard card.
- Added deterministic edge, controller, and widget coverage.
- Bumped the source-only edge-agent version to 0.13.0.

## Reason

Make all physical and network paths visible before health assessment and repair.

## Dependencies

No new runtime dependency. The map uses existing Linux interface and device
paths; future Bluetooth/NFC activation remains separate.

## Future implications

Connection events, model assessment unification, and remote enrollment can now
refer to stable transport and capability identifiers.
