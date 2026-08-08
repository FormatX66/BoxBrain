# BoxBrain Dual Queue Sync

BoxBrain uses both a Git-backed queue and a local Desktop fallback.

## Locations

Git:
- `.codex/queue/QUEUE.md`
- `.codex/queue/COMPLETE.md`

Local Windows fallback:
- `%USERPROFILE%\Desktop\Codex Cue.txt`
- `%USERPROFILE%\Desktop\Cue Complete.txt`

Local macOS fallback:
- `~/Desktop/Codex Cue.txt`
- `~/Desktop/Cue Complete.txt`

Runtime/local-only state:
- `.boxbrain/codex-queue-state.json`
- `.boxbrain/codex-usage-events.jsonl`
- `.boxbrain/codex-queue.lock`

## Why both

Git provides shared history and synchronization between machines/agents. The local queue remains operational when Git/network access is unavailable or when a usage cap prevents normal remote interaction.

## Desktop bootstrap

When `run queue` is invoked on a Windows PC or macOS computer, first check whether the local Desktop queue files exist.

If `Codex Cue.txt` does not exist locally and Git is reachable:
1. Fetch `.codex/queue/QUEUE.md`.
2. Create a local Desktop `Codex Cue.txt` containing the current reconciled queue.
3. Preserve the same stable `BB-###` task IDs and task statuses.
4. Continue the normal local + Git preflight.

If `Cue Complete.txt` does not exist locally and Git is reachable:
1. Fetch `.codex/queue/COMPLETE.md`.
2. Create the local Desktop `Cue Complete.txt` from that verified completion history.
3. Continue normal reconciliation.

If the local file is missing and Git is temporarily unavailable, do not invent an empty authoritative queue. Use an existing cached/runtime copy if one is available. Otherwise report that the queue cannot yet be reconstructed locally and retry synchronization when Git becomes reachable.

This Desktop bootstrap behavior applies only to Windows and macOS interactive workstation instances. Do not create Desktop queue copies automatically on Raspberry Pi, headless Linux, servers, containers, or CI runners.

A newly imported local copy is a mirror/fallback, not a replacement for the Git queue. Subsequent changes must reconcile both directions by stable task ID rather than blindly overwriting either side.

## Reconciliation

On `run queue`, load both sides when possible and merge by stable `BB-###` task ID. Do not blindly copy one file over the other. Preserve newer explicit user requirements and verify the actual repository before deciding a task is complete.

If Git is unavailable, process the local queue and record local state/checkpoints. When Git becomes reachable, reconcile those changes back into `QUEUE.md`/`COMPLETE.md`.

## Completion

A task is complete only when its acceptance criteria verify against the current repository/system. Completed tasks are logged in both Git `COMPLETE.md` and local `Cue Complete.txt` when both are available.

## Usage caps

If a required capability is capped, mark the task `DEFERRED_USAGE`, checkpoint it locally, schedule one legitimate retry when possible, and continue using local queue/state. Do not repeatedly retry the capped service. On later availability, re-run preflight and synchronize state back to Git.

## Source-of-truth order

1. Actual repository/system behavior
2. Verified completion records
3. Reconciled Git/local task definition
4. Runtime state/checkpoints

Git is the preferred shared copy; local storage is the resilient fallback.
