# Verification Checklist — BB-2026-07-28-002

- [x] BrainConnect began from clean revision `1c6c926`
- [x] Work isolated on `feature/brainconnect-live-events`
- [x] HTTP routes remain bearer-authenticated
- [x] WebSocket releases no events before authentication
- [x] Invalid token closes with `4401`
- [x] Untrusted browser origin closes with `4403`
- [x] Cursor resume and delivery of newly created events tested
- [x] Flutter token is not placed in the WebSocket URL
- [x] Flutter reconnect resumes from the latest sequence
- [x] Polling fallback deduplicates by sequence
- [x] Backend tests pass: 12 tests
- [x] Flutter analysis reports no issues
- [x] Flutter tests pass: 6 tests
- [x] Production Flutter web build succeeds
- [x] Real loopback HTTP task to WebSocket audit exchange passes
- [x] Runtime token, database, certificates, and build output remain ignored
- [x] BoxBrain required files, links, and orphan checks pass
- [x] BrainConnect feature commit created: `9515d02`

The web build retains the pre-existing non-blocking CupertinoIcons font warning.
The backend suite retains one upstream Starlette TestClient migration warning.
