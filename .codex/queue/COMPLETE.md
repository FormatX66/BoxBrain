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
COMMIT: 39eec10
NOTES:
The existing upstream Starlette TestClient migration warning remains non-failing and is not a BB-006 regression. No provider usage numbers were invented; metrics count observed local model-call avoidance only.
==================================================

[TASK BB-990]
STATUS: COMPLETE
TITLE: Verify one-time Git-to-local bridge wake-up
TASK_TYPE: READ_ONLY_REPOSITORY_STATUS
EXECUTOR: readonly-repository-status
COMPLETED_AT: 2026-08-12T05:27:06.6026639+00:00
VERIFIED: true
RESULT: Read-only repository status verified at commit 4cea893a6f78; tracked_files=579; dirty_entries=0.
TASK_HASH: eccc039b374d10fd3ce7ceb96e73752d69f48b85dbf87396fd4890b4913ee98c
RESULT_HASH: 058237e57be17b7bb88249a5c10e45f8f49a140839d5cb57b88280e43002bc54
DISPATCHER_HASH: 958a279226aa05883c3d877e0d0d4f03efc02dc283bc983916067a204a789ff6
END TASK

==================================================
TASK: BB-009
TITLE: Deploy Codelation Seed to BBPI4
STATUS: COMPLETE
COMPLETED: 2026-08-12T10:32:52Z
VERIFIED: YES
IMPLEMENTED:
- Installed the passive seed at `/opt/boxbrain/codelation` through the established pinned-key LAN route.
- Preserved least-privilege `kali:kali` ownership and mode `700` on the installation root.
- Left network authority, actuation, autorun, systemd, and cron disabled.
TESTS:
- Local `python -m unittest discover -s Projects/Codelation/tests -v`: 3 passed.
- Pi `python3 -m unittest discover -s tests -v`: 3 passed.
- Pi `python3 seed/codelation_seed.py summary --model seed.bin`: succeeded with version 1 and an empty passive graph.
- Pi Python: 3.13.12.
- Temporary transfer directories: 0 remaining.
- Codelation systemd units and cron entries: 0.
FILES:
- /opt/boxbrain/codelation
COMMIT: bab09a5 (verified deployment source)
NOTES:
The deployment enables no background execution or action authority. The binary model remains empty until an explicitly invoked observation is recorded.
==================================================
