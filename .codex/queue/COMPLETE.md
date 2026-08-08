# BoxBrain Codex Queue — Verified Complete

Append-only human-readable history of tasks from `.codex/queue/QUEUE.md` that have been verified complete.

A task is recorded here only after the implementation exists, applicable tests pass, integration is verified, and acceptance criteria are satisfied.

Before skipping a task because it appears here, Codex must verify that the current repository/system still satisfies the task. If it has regressed or disappeared, reopen the task.

## Completion record format

```text
==================================================
TASK: BB-XXX
TITLE: <title>
STATUS: COMPLETE
COMPLETED: <timestamp>
VERIFIED: YES
IMPLEMENTED:
- ...
TESTS:
- ...
FILES:
- ...
COMMIT: <sha if applicable>
NOTES:
...
==================================================
```

## Completed tasks

==================================================
TASK: BB-006
TITLE: Script-First Task Offload / GPT Usage Reduction
STATUS: COMPLETE
COMPLETED: 2026-08-08T06:40:23Z
VERIFIED: YES
IMPLEMENTED:
- Added Script/GPT/Hybrid classification with confidence, reasons, fallback, human-review gates, and future model-lane metadata.
- Added a versioned registry for deterministic text summaries, JSONL summaries, bounded diffs, and repository-bounded file inventories.
- Added structured results, exception-driven GPT escalation, persistent idempotency, and Cue Complete duplicate prevention.
- Added append-only route/run metrics for avoided model calls, reliability, duration, errors, escalations, and prevented duplicates.
- Added authenticated controller API endpoints and documented contracts, security boundaries, permissions, and rollback policy.
TESTS:
- `pytest -q tests/test_script_first.py`: 6 passed.
- `pytest -q` in `controller`: 97 passed.
FILES:
- controller/src/boxbrain_controller/script_first.py
- controller/src/boxbrain_controller/api.py
- controller/src/boxbrain_controller/settings.py
- controller/tests/test_script_first.py
- docs/SCRIPT_FIRST_ROUTING.md
- controller/README.md
COMMIT: pending queue synchronization commit
NOTES:
The existing upstream Starlette TestClient migration warning remains non-failing and is not a BB-006 regression. No provider usage numbers were invented; metrics count observed local model-call avoidance only.
==================================================
