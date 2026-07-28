# Change Log — BB-2026-07-28-002

## BrainConnect

- Added `event_stream.py` with authenticated, origin-checked, resumable audit
  delivery.
- Split HTTP bearer dependencies from the WebSocket route while preserving
  authentication on every HTTP API.
- Added bounded authentication payload validation.
- Added Flutter WebSocket transport, scheme mapping, authentication, parsing,
  reconnect, cursor resume, and sequence deduplication.
- Added `web_socket_channel` and its locked transitive dependencies.
- Added four backend stream security/delivery tests and two Flutter
  transport/reconnect tests.
- Updated root, controller, architecture, development, roadmap, and security
  documentation.

## BoxBrain

- Updated repository, roadmap, TODO, project, decision, change, session, and
  integration indexes.
- Updated the validator to require every correctly named session directory.
- Added the complete `BB-2026-07-28-002` handoff bundle.

## Reason

Complete BrainConnect milestone 0.2 live audit delivery without enabling target
observation or input execution.

## Dependencies

- FastAPI/Starlette WebSocket support
- SQLite monotonic audit sequence
- Flutter `web_socket_channel` 3.0.3
- Existing bearer token and polling APIs

## Future implications

- Target registry events will automatically appear live once implemented.
- Production browser authentication must replace embedded development tokens.
- Reconnect backoff and UI event retention need operational limits.
- Observation transports remain blocked on target identity and allowlisting.
