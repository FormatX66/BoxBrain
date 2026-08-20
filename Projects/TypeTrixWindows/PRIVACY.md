# TypeTrix Privacy Boundary

TypeTrix is designed around a strict distinction between **interaction structure** and **content**.

## v0 rules

- The TSF adapter records no raw characters.
- Structural key classes (input activity, backspace, delete, navigation) are processed only in memory.
- No typed transcript is written to disk.
- No network service is contacted.
- No medical or learning-disability inference is produced.
- No keystroke is consumed or rewritten by the v0 adapter.

## Before contextual suggestions are enabled

The project must add and test:

1. protected/password-field suppression;
2. per-application/private-mode controls;
3. short-lived context buffers with explicit lifetime bounds;
4. local encrypted personalization storage where durable state is needed;
5. one-action pause/reset/delete controls;
6. audit tests proving no raw text enters logs/telemetry;
7. explicit policy for optional cloud inference, disabled by default.

## Durable learning

Durable personalization should store derived information whenever possible: confusion pairs, recurring edit patterns, accepted vocabulary, timing baselines and suggestion feedback. A user may explicitly choose to retain words or examples for coaching, but that must be distinguishable from silent background collection.

The user's personal model should be exportable, resettable and deletable.
