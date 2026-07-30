# Decision Log

## BB-ADR-032

- **Date:** 2026-07-29
- **Decision:** For headless control of this local Windows target, bind the
  credential to `BB-WIN-LAB`, request the existing console session, force
  slow-path input, and fail when input is suspended.
- **Reason:** Windows events proved authentication and session reconnection,
  while fast-path calls returned transport success without target-state
  changes. Slow-path delivery produced independently verified Task Manager and
  Notepad processes.
- **Alternatives considered:** More key delays, arbitrary unlock/password
  keystrokes, weakening the one-session policy, installing a different remote
  desktop server, and treating FreeRDP acceptance as success.
- **Chosen solution:** Retain the pinned FreeRDP boundary and correct its
  identity, session-selection, and input-delivery settings.
- **Impact:** Keyboard control now reaches the intended disposable desktop
  without expanding the credential or policy boundary. Frame verification is
  still required for cursor and visible-content claims.

## BB-ADR-033

- **Date:** 2026-07-29
- **Decision:** Accept an optional UTF-8 byte-order marker only at the local
  Windows experiment-plan file boundary.
- **Reason:** Windows tooling can emit UTF-8 BOM files even when the JSON
  content is otherwise canonical and valid.
- **Alternatives considered:** Reject all BOM files, normalize every controller
  payload, or loosen downstream JSON parsing.
- **Chosen solution:** Decode the local plan with `utf-8-sig`, then apply the
  existing strict schema and payload validation unchanged.
- **Impact:** Operator-generated Windows plans are reliable without weakening
  the controller or adapter protocols.
