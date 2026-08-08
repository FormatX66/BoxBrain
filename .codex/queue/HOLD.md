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

## Held Ideas

[HOLD BH-001]
STATUS: HOLD
TITLE: Multi-GPT Revolving Cycle

WHY ON HOLD:
The concept needs architecture, account/usage-limit handling, model-routing rules, and implementation details before it is ready to build.

NOTES:
Design a revolving multi-ChatGPT workflow that can distribute work across multiple available ChatGPT sessions/accounts or execution lanes instead of allowing a single exhausted usage window to stop the larger workflow. The orchestration layer should know which lane is available, which usage/cap type is exhausted, and when each lane is expected to become usable again. Work should move to another eligible lane when appropriate while preserving task state and context.

The concept should integrate with the Codex Cue system. If a task cannot run because the currently selected GPT/session has reached the relevant usage cap, determine whether another authorized lane can perform the task. If so, hand the task off without duplicating completed work. If no lane is currently eligible, keep the task queued and associate it with the appropriate future rolling-cycle availability rather than repeatedly consuming attempts.

Future design should consider:
- Multiple authorized ChatGPT sessions/accounts or model lanes.
- Per-lane usage/cap awareness and reset-cycle tracking.
- Automatic routing to an eligible lane based on task requirements and remaining capability.
- Preservation of task state, context, artifacts, logs, and completion checks during handoff.
- Duplicate-work prevention by checking Cue Complete and current task state before execution.
- Local/Git queue continuity when cloud/model access is unavailable.
- Safe authentication and strict separation of credentials between accounts/machines.
- A scheduler/orchestrator that revisits held or blocked tasks when the applicable rolling cycle becomes available.
- Clear audit logs showing which lane handled each task and why routing changed.
- Rules for tasks that require a specific model/capability and therefore cannot simply move to another lane.

PROMOTION CRITERIA:
- Define the exact meaning of a GPT/session/account "lane."
- Determine what usage/reset information can be observed reliably and legally.
- Define routing, retry, and anti-duplication rules.
- Define secure credential/session handling.
- Define integration with Codex Cue, Cue Hold, and Cue Complete.
- User explicitly promotes the concept to the active queue.

END HOLD

## Promotion Flow

`Cue Hold` -> explicit promote command -> active `Codex Cue` task -> build/test/verify -> `Cue Complete`

The repository/system remains the final source of truth for implementation state.
