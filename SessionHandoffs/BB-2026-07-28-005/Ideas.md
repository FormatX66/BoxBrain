# Ideas

- Build the native helper in a pinned container or VM so Windows development,
  Kali, and Raspberry Pi packages are produced from one documented baseline.
- Add a fake TLS/RDP fixture that can rotate between two test certificates
  without requiring a long-lived lab machine.
- Store a build provenance record beside the helper package without storing
  certificates, credentials, or frame data.
- Add a UI comparison view for the approved and observed certificate metadata
  after a mismatch while keeping the target disabled.
- Add a short-lived probe lease so concurrent operator requests cannot create
  duplicate network probes for the same target.
- Add signed release checksums for native helper packages.
