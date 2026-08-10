# Decision Log

## BB-ADR-053

- **Date:** 2026-08-03
- **Decision:** Treat the Raspberry Pi 4 as the canonical BoxBrain core
  appliance and owner of durable runtime state plus physical transports.
- **Reason:** The product must remain usable when attached to a target without
  depending on the operator's Windows workstation.
- **Alternatives considered:** Keep Windows as the core controller; split
  identity across a Windows controller and a Pi edge agent.
- **Chosen solution:** Consolidate the canonical runtime identity on the Pi and
  embed compatible BrainConnect controller components there.
- **Impact:** UI, state, and transport work now converge on the Pi appliance.

## BB-ADR-054

- **Date:** 2026-08-03
- **Decision:** Expose USB keyboard and mouse as separate ConfigFS HID functions
  while treating Bluetooth HID as a separate explicit pairing boundary.
- **Reason:** USB enumeration is physical and deterministic; Bluetooth requires
  discovery, pairing, bonding, and host trust that USB insertion cannot imply.
- **Alternatives considered:** Keyboard-only USB; automatic Bluetooth pairing on
  every USB insertion; one vendor-specific combined HID report.
- **Chosen solution:** Standard boot keyboard and three-button relative mouse
  endpoints alongside RNDIS, with Bluetooth left disabled until policy approval.
- **Impact:** Windows receives standard HID devices without a driver, while
  nearby Bluetooth devices cannot silently become trusted.
