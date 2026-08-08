# BoxBrain Cue Hold

This file stores ideas, future implementations, experiments, and partially formed specifications that are intentionally **not ready to build**.

## Rules

- `run queue` MUST NOT execute items from this file.
- Hold items may be read for context and duplicate detection only.
- Each hold item should have a stable ID, preferably `BH-###` for BoxBrain Hold.
- Hold items may include notes, open questions, dependencies, references, and proposed acceptance criteria.
- A hold item becomes active only when the user or an authorized project workflow explicitly promotes it to the active queue.
- Promotion should preserve the original hold ID in the new task record for traceability and assign a normal active `BB-###` task ID.
- Do not silently promote an idea because it seems easy or useful.
- Hold items should synchronize between Git and local Desktop copies just like the active queue, but they are never considered runnable work.

## Suggested Format

```text
[HOLD BH-001]
STATUS: HOLD
TITLE: Example future feature

WHY ON HOLD:
Needs more design work.

NOTES:
Preserve the idea here without scheduling implementation.

PROMOTION CRITERIA:
- Architecture decided
- Dependencies identified
- User explicitly promotes to queue

END HOLD
```

## Promotion Flow

`Cue Hold` -> explicit promote command -> active `Codex Cue` task -> build/test/verify -> `Cue Complete`

The repository/system remains the final source of truth for implementation state.
