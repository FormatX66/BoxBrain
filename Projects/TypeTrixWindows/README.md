# TypeTrix for Windows

TypeTrix is a standalone Windows implementation of Aurum's adaptive typing/help concept. It is designed to help immediately while teaching along the way.

## North-star behavior

- Detect friction, not merely spelling mistakes.
- Use context and the user's own interaction patterns to infer likely intent.
- Treat backspace/retype bursts, hesitation, abandoned word attempts, repeated phonetic attempts, and rejected suggestions as useful signals.
- Offer help non-disruptively and only when confidence justifies it.
- Separate immediate assistance from optional coaching.
- Preserve the user's voice and vocabulary.
- Keep personal interaction models local/private by default.
- Never infer or diagnose a medical/learning condition from typing behavior.

## Windows integration

The intended Windows integration is a **Text Services Framework (TSF) text service**, rather than a global low-level keyboard hook. TSF is Windows' system framework for advanced text input/language services and provides a proper path for text services to receive input events, maintain compositions, and present candidates.

The project is split into two layers:

1. `core/` — platform-neutral friction detection, personalization, confidence and coaching logic.
2. `windows/tsf/` — Windows TSF adapter that turns edit/input events into core signals and presents suggestions.

This separation lets the same capability later become an Aurum TR8/Trix without preserving Windows-specific abstractions.

## First milestone

A Windows prototype should:

1. install as an explicitly enabled text service;
2. observe structural edit behavior in supported text surfaces;
3. detect a probable word-search episode from backspace/retype/pause patterns;
4. show a small nonblocking candidate surface;
5. record accept/reject/undo feedback locally;
6. expose an optional "teach me" mode that turns recurring friction into tiny practice moments.

## Privacy defaults

TypeTrix should not be a keylogger. Raw text retention is not the default. Context needed for a live suggestion should be ephemeral wherever possible; durable personalization should prefer derived patterns, counters, hashes/identifiers where useful, and explicit user-approved vocabulary over storing complete typed history.

Sensitive/password fields must be excluded.

## Status

This branch is the repo-ready side project scaffold. The core detector is intentionally independent from TSF so it can be tested before system-wide integration is enabled.
