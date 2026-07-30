# Decision Log

## BB-ADR-011

- **Date:** 2026-07-28
- **Decision:** Deploy the reviewed arm64 helper to the Raspberry Pi only after
  checking the exact host architecture and FreeRDP package version and passing
  the complete native boundary test on that host. Record content-addressed
  provenance beside the root-owned binary.
- **Reason:** The helper was built against FreeRDP 3.15, while Kali already
  carried FreeRDP 3.26. Loading through the same major ABI was not sufficient
  evidence for a security boundary. The selected-protocol, callback, deadline,
  and no-authentication behavior had to be repeated on the actual runtime
  before installation.
- **Alternatives considered:** Upgrade Kali to its FreeRDP 3.30 candidate,
  downgrade or hold host packages, install Docker on the Pi, compile against
  Kali's headers, bundle the entire Debian multimedia dependency tree, copy the
  ELF without testing, or trust a mutable image tag without a digest.
- **Chosen solution:** Extract the reviewed ELF from the local arm64 Docker
  image, record the image ID and ELF SHA-256, require Kali's exact
  `3.26.0+dfsg-1` package version, run the synthetic integration suite from a
  unique temporary path, refuse an unexpected existing binary, install
  root-owned files, and verify the installed checksum. Make no package change.
- **Impact:** The Pi now has a reproducible, auditable certificate helper
  installation. Runtime drift and binary replacement fail closed in the
  installer. Controller deployment and a live isolated Windows probe remain
  separate milestones.
