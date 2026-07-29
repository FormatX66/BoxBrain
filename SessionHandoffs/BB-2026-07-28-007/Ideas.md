# Ideas

- Add a controller startup check that compares the current helper checksum and
  FreeRDP package version with the provenance record.
- Add a signed provenance envelope before producing public release artifacts.
- Expose a localhost-only readiness endpoint that distinguishes controller,
  database, audit, and helper health without probing a target.
- Package the controller as a versioned wheel and lock file rather than copying
  a mutable checkout.
- Use a dedicated `brainconnect` service account with read-only access to the
  helper and write access only to bounded runtime directories.
- Add a USB-link health monitor that records disconnects without automatically
  restarting network observations.
