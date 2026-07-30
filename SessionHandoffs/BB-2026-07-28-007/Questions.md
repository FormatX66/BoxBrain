# Questions

## Open

- Should the next milestone deploy the FastAPI controller on the Pi or select
  and prepare the isolated Windows RDP target first?
- May the next milestone create and enable a hardened systemd service after
  foreground verification?
- Which interface should the Pi controller bind to: loopback only, the direct
  USB gadget address, or another explicitly isolated interface?
- Which isolated Windows VM will provide the exact-match and
  changed-certificate live fixtures?
- Should the existing public BoxBrain remote remain public after the canonical
  organization is merged?

## Resolved this session

- The intended Pi is the directly attached Raspberry Pi 4 at `10.12.194.1`.
- Existing key-based SSH access uses username `kali` and strict host identity.
- The Pi runtime is Kali 2026.2 arm64 with FreeRDP package
  `3.26.0+dfsg-1`.
- The host runtime passes the full native certificate-boundary fixture.
- The helper is installed root-owned with checksum and content-addressed
  provenance.
- No package change or package hold was needed.
