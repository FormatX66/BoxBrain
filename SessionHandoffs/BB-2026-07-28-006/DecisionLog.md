# Decision Log

## BB-ADR-010

- **Date:** 2026-07-28
- **Decision:** Pin the native certificate helper to the Debian 13 FreeRDP
  3.15.x ABI and emit certificate observations only when the RDP server's
  selected security protocol is exactly NLA/HYBRID.
- **Reason:** FreeRDP's NLA attempt advertises both SSL and HYBRID. Trusting the
  requested mask would allow a server-selected TLS-only downgrade to reach the
  certificate output path. Pinning the ABI keeps callback ownership and
  settings behavior reproducible across amd64 and arm64.
- **Alternatives considered:** Require the request mask to contain only
  HYBRID, accept TLS-only certificate observation, run a generic `xfreerdp`
  command, enable certificate-ignore or trust-on-first-use, install compilers
  directly on the Windows workstation, and track unpinned FreeRDP releases.
- **Chosen solution:** Build in a digest-pinned Debian 13 container, require
  FreeRDP 3.15.x at CMake configure time, enable external certificate
  management, inspect `FreeRDP_SelectedProtocol`, accept only
  `PROTOCOL_HYBRID`, extract bounded metadata, and always reject the
  certificate callback. Test the same behavior on amd64 and arm64, including a
  TLS-only server response.
- **Impact:** The helper can prove endpoint certificate identity without
  authentication or a desktop session and fails closed on protocol downgrade.
  FreeRDP upgrades, new architectures, host packaging, and live Windows tests
  remain explicit review milestones.
