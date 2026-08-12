# Git-to-local Codex bridge

The bridge lets a cloud or mobile session publish a stable BoxBrain task through
Git and lets Bruce's signed-in Windows account receive it without manually
copying prompts. It is intentionally script-first: queue text is data, never a
shell program.

## Security boundary

The Windows watcher fetches only the locally approved `FormatX66/BoxBrain`
remote and branch. It accepts only `BB-###` task IDs, bounded task blocks, known
statuses, and a locally hash-pinned read-only dispatcher. Queue fields such as
`COMMAND`, `SHELL`, `SCRIPT`, `ARGS`, path traversal, credential requests, and
destructive requests are rejected before dispatch.

The checked-in `dispatchers.json` file is a proposal, not authority. Installation
requires the local `-ApproveDispatcherManifest` switch, then copies each reviewed
script into LocalAppData and records its SHA-256 hash in a local trust registry.
A later Git change cannot update that registry. A new or changed dispatcher stays
rejected until Bruce reviews it and reruns the installer with explicit approval.

The bridge never writes authentication material to Git, Desktop queue mirrors,
logs, command arguments, or pending-work prompts. Structured local logs redact
secret-like values and bound every field.

## Publish from cloud or mobile Codex

Create or update one task block in `.codex/queue/QUEUE.md`, commit it, and push it
to the configured bridge branch. A deterministic task must name an approved task
type and executor:

```text
[TASK BB-990]
STATUS: PENDING
TITLE: Report repository status
TASK_TYPE: READ_ONLY_REPOSITORY_STATUS
EXECUTOR: readonly-repository-status
END TASK
```

Do not include commands, credentials, local absolute paths, or executable script
content. Task IDs are stable: continue partial work under the same ID and add a
bounded `CHECKPOINT` plus ISO-8601 `CHECKPOINT_AT`. A materially changed task has
a new content hash and is reconsidered; an exact verified task is not repeated.

## Receive and return results

At interactive Windows logon, Task Scheduler starts one hidden watcher under the
existing account. The watcher polls while the PC is awake, takes an atomic
single-instance lock, fetches the configured branch, and reconciles:

- Git `.codex/queue/QUEUE.md` and `.codex/queue/COMPLETE.md`
- Desktop `Codex Cue.txt` and `Cue Complete.txt`
- the local hash-pinned execution state

Conflicting task bodies are not guessed away. When both have timestamps, the
latest checkpoint wins; otherwise the task is surfaced for review. Verified
completion requires matching task, result, and dispatcher hashes.

An approved dispatcher receives only a validated task ID, the isolated repository
root, and a bridge-owned result path. On success, the watcher removes the active
task, appends a bounded verified record to `COMPLETE.md`, mirrors those changes to
the Desktop files, commits only the two queue records, and pushes them. A saved
`RESULT_READY` checkpoint is validated and republished after a transient failure
without running the dispatcher again.

Reasoning tasks use `TASK_TYPE: REASONING` and `EXECUTOR: codex`. Unless a
separately reviewed supported non-interactive Codex dispatcher is locally
installed, the watcher does not automate the UI or bypass sign-in. It writes a
clear `BoxBrain Pending Codex Work.txt` notification on the Desktop for the
existing Remote BoxBrain project workflow.

## Install and control

From a clean checkout of the branch to watch, first review
`installer/codex-bridge/dispatchers.json` and every referenced script. Then run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\installer\install-git-local-codex-bridge.ps1 `
  -RemoteBranch agent/git-local-codex-bridge `
  -ApproveDispatcherManifest -StartNow
```

The current-user installation lives under
`%LOCALAPPDATA%\BoxBrain\CodexBridge`. It uses an isolated clean clone, so it does
not modify a development checkout or unrelated local changes.

Use the management command for lifecycle and diagnostics:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\manage-git-local-codex-bridge.ps1 -Action Status
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\manage-git-local-codex-bridge.ps1 -Action Health
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\manage-git-local-codex-bridge.ps1 -Action Start
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\manage-git-local-codex-bridge.ps1 -Action Stop
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\manage-git-local-codex-bridge.ps1 -Action Restart
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\manage-git-local-codex-bridge.ps1 -Action Poll
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\manage-git-local-codex-bridge.ps1 -Action DryRun
```

Run automated tests before approval or reinstall:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\test-git-local-codex-bridge.ps1
```

Uninstall the scheduled watcher and installed executable copies while preserving
local evidence by default:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\installer\uninstall-git-local-codex-bridge.ps1
```

Add `-RemoveLocalState` only when the isolated clone, logs, results, backups, and
execution state should also be removed.

## Diagnose and recover

`Status` reports the scheduled task state, last Task Scheduler result, bridge
health timestamp, and pending count. Local evidence is stored in:

- `state\health.json` — last bounded health report
- `state\bridge-state.json` — task hashes, checkpoints, and execution counts
- `logs\bridge.jsonl` — structured redacted events
- `results\` — bounded dispatcher results
- `backups\` — pre-update queue mirrors

Fetch failures use exponential backoff and recover automatically. A dead process
or aged lock is renamed as stale evidence and replaced atomically. For an ordinary
stopped task, run `Restart`; for a one-cycle diagnostic, stop it and use `DryRun`
or `Poll`. If the isolated clone has an unrelated change or a Git conflict, leave
the watcher stopped, inspect that clone, preserve its state and backups, then
reinstall from a reviewed clean checkout. Never resolve such a condition by
granting queue text executable authority.
