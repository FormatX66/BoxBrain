# Ideas

- Produce signed `.deb` packages for amd64 and arm64 from the pinned build
  stage.
- Add an evidence manifest containing source revision, image digest, package
  checksum, target UUID, redacted endpoint, and audit sequence range.
- Automate RDP certificate rotation in the disposable Windows fixture so exact
  match and mismatch are repeatable.
- Add a protocol-selection matrix fixture for HYBRID, SSL, RDP, RDSTLS,
  HYBRID_EX, malformed, and negotiation-failure responses.
- Sign release checksums separately from the runtime package.
- Add CI after the stacked branches merge so native amd64 tests run on every
  change and arm64 runs on native or emulated infrastructure.
