# Human Handoff — BB-2026-07-28-002

## What was accomplished

- Added an authenticated BrainConnect WebSocket for live audit delivery.
- Added five-second first-message authentication, constant-time token
  validation, browser-origin checks, sequence resume, event batching, and idle
  keepalives.
- Added a cross-platform Flutter client that maps HTTP to WebSocket schemes,
  authenticates without placing the token in the URL, reconnects from the last
  sequence, and deduplicates events.
- Retained the existing HTTP event cursor as a fallback.
- Added backend, transport, and widget tests and completed a real loopback
  HTTP-to-WebSocket exchange.
- Committed BrainConnect revision `9515d02`.

## Decisions made

- Use WebSocket rather than server-sent events because Flutter web’s standard
  browser HTTP client cannot reliably consume an infinite header-authenticated
  response.
- Keep cursor-based polling as a fallback until live delivery has production
  operating history.

See the [canonical decision log](DecisionLog.md).

## Current blockers

- Neither BoxBrain nor BrainConnect has a configured remote repository.
- Target identity fields, allowlisting workflow, and observation protocol are
  not yet chosen.
- The current FastAPI/Starlette test stack emits an upstream TestClient
  migration warning.

## Immediate next step

Define the observation-target identity and allowlist model without adding input
execution.

## Long-term objective

Deliver an auditable research controller that can observe and later perform
bounded, verified actions in explicitly authorized disposable environments.
