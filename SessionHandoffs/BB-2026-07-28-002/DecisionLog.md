# Decision Log — BB-2026-07-28-002

## BB-ADR-004

- **Date:** 2026-07-28
- **Reason:** The dashboard needs live authenticated events on Flutter web,
  desktop, and later mobile without placing credentials in a URL.
- **Alternatives considered:** Server-sent events with an Authorization header;
  native browser `EventSource` with a query token; WebSocket subprotocol token;
  first-message WebSocket authentication.
- **Chosen solution:** Use a WebSocket that releases no data until a validated
  authentication message arrives within five seconds.
- **Impact:** One client works across Flutter platforms, tokens stay out of
  URLs, browser origins are checked, and reconnect uses the audit sequence.
  Production still requires TLS and browser-safe session authentication.

## BB-ADR-005

- **Date:** 2026-07-28
- **Reason:** A new streaming path must not make audit visibility depend on a
  single long-lived connection.
- **Alternatives considered:** Replace polling immediately; keep independent
  live and polling lists; retain polling with sequence deduplication.
- **Chosen solution:** Continue the three-second cursor poll and merge both
  paths by the immutable database sequence.
- **Impact:** Temporary WebSocket failures do not hide events. The extra local
  read load is accepted until live delivery has operational history.
