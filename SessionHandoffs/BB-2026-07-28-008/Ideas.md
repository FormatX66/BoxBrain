# Ideas

- Add an authenticated readiness response that reports configured helper
  provenance without contacting an RDP target.
- Add a short-lived dashboard session exchange so the long-lived Pi bearer
  token never enters a Flutter web build.
- Add an upgrade command that stages a new release, runs the foreground gate,
  atomically switches `current`, and rolls back the symlink if service health
  fails.
- Cache reviewed Python wheels with hashes for offline and fully
  content-addressed Pi deployment.
- Add a USB-link health monitor that records disconnects without automatically
  initiating target observations.
- Export signed, redacted audit bundles before and after disposable live-lab
  runs.
