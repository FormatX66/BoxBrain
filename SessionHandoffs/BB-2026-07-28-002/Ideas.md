# Ideas — BB-2026-07-28-002

- Show live-stream connected, reconnecting, and polling-fallback status in the
  dashboard.
- Add bounded exponential reconnect backoff with jitter.
- Cap in-memory dashboard events while preserving cursor correctness.
- Add an authenticated session exchange before any non-local browser
  deployment so bearer tokens are not compiled into Flutter output.
- Export signed audit checkpoints for stronger tamper evidence.
- Add an integration test that launches the controller and Flutter web client
  in CI after remote hosting is configured.

Ideas are not commitments. Promote them through a decision and prioritized
task before implementation.
