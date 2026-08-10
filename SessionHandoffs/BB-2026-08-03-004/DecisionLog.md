# Decision Log

## BB-ADR-056

- **Date:** 2026-08-03
- **Reason:** BoxBrain needs a recovery path that survives loss of the normal
  Wi-Fi network before USB gadget changes are activated.
- **Alternatives considered:** Replace `wlan0` with a hotspot; rely only on USB
  Ethernet; require a second Wi-Fi adapter; create a virtual AP beside the
  existing managed connection.
- **Chosen solution:** Create `bbap0` on the physical radio's current channel,
  assign `10.42.194.1/24`, generate a root-only WPA2/CCMP key, provide DHCP,
  reject forwarding into other interfaces, and use preview/stage/commit/rollback
  gates. Activate composite RNDIS, keyboard, and mouse only after that fallback
  is healthy.
- **Impact:** The Pi retains its normal Wi-Fi and USB paths while advertising a
  device-local recovery network. Client and AP channels remain coupled because
  the Pi has one Wi-Fi radio.
