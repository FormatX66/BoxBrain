# BoxBrain Dual Queue Sync

BoxBrain uses a Git-backed queue plus local Desktop mirrors/fallbacks.

## Locations

Git:
- `.codex/queue/QUEUE.md` — active runnable work
- `.codex/queue/HOLD.md` — ideas/specs not ready to build
- `.codex/queue/COMPLETE.md` — verified completed work

Queue indexes:
- [Active runnable work](QUEUE.md)
- [Held ideas and specifications](HOLD.md)
- [Verified completed work](COMPLETE.md)

Local Windows fallback:
- `%USERPROFILE%\Desktop\Codex Cue.txt`
- `%USERPROFILE%\Desktop\Cue Hold.txt`
- `%USERPROFILE%\Desktop\Cue Complete.txt`

Local macOS fallback:
- `~/Desktop/Codex Cue.txt`
- `~/Desktop/Cue Hold.txt`
- `~/Desktop/Cue Complete.txt`

Runtime/local-only state:
- `.boxbrain/codex-queue-state.json`
- `.boxbrain/codex-usage-events.jsonl`
- `.boxbrain/codex-queue.lock`

## Three-lane model

`Codex Cue / QUEUE.md` is active runnable work.

`Cue Hold / HOLD.md` preserves future ideas, experiments, and incomplete implementation concepts. `run queue` MUST NOT execute hold items. Hold items may be read only for context and duplicate detection until explicitly promoted.

`Cue Complete / COMPLETE.md` is the verified completion history.

Promotion flow:
`Cue Hold` -> explicit promotion -> active `Codex Cue` task -> build/test/verify -> `Cue Complete`.

Use stable `BH-###` IDs for hold entries and stable `BB-###` IDs for active tasks. When promoting a hold entry, preserve the source `BH-###` reference in the active task for traceability.

## Why both Git and local

Git provides shared history and synchronization between machines/agents. Local files remain operational when Git/network access is unavailable or when a usage cap prevents normal remote interaction.

## Desktop bootstrap

When `run queue` is invoked on a Windows PC or macOS computer, first check whether the local Desktop queue files exist.

If `Codex Cue.txt` does not exist locally and Git is reachable, fetch `.codex/queue/QUEUE.md` and create the Desktop mirror.

If `Cue Hold.txt` does not exist locally and Git is reachable, fetch `.codex/queue/HOLD.md` and create the Desktop mirror.

If `Cue Complete.txt` does not exist locally and Git is reachable, fetch `.codex/queue/COMPLETE.md` and create the Desktop mirror.

Preserve stable IDs, statuses, dependencies, acceptance/promotion criteria, notes, and checkpoints.

If a local file is missing and Git is temporarily unavailable, do not invent an empty authoritative file. Use an existing cached/runtime copy if available; otherwise retry reconstruction when Git becomes reachable.

Desktop bootstrap applies only to Windows/macOS interactive workstations. Do not create Desktop queue copies automatically on Raspberry Pi, headless Linux, servers, containers, or CI runners.

## Reconciliation

On `run queue`, load Git/local ACTIVE and COMPLETE sources when possible. Also load HOLD for duplicate/context checks but never as executable work. Merge records by stable IDs rather than blindly overwriting files.

If Git is unavailable, process the local active queue and record local state/checkpoints/completions. Hold entries remain non-runnable locally as well. When Git becomes reachable, reconcile all three lanes back to Git.

## Completion

A task is complete only when its acceptance criteria verify against the current repository/system. Completed tasks are logged in both Git `COMPLETE.md` and local `Cue Complete.txt` when both are available.

## Usage caps

If a required capability is capped, mark the active task `DEFERRED_USAGE`, checkpoint locally, schedule one legitimate retry when possible, and continue using local queue/state. Do not repeatedly retry the capped service. Do not move deferred work into Hold merely because of a usage limit; Hold means not ready by design, not temporarily unavailable.

## Source-of-truth order

1. Actual repository/system behavior
2. Verified completion records
3. Reconciled Git/local active or hold definition
4. Runtime state/checkpoints

Git is the preferred shared copy; local storage is the resilient fallback.
