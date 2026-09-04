# Future Branch live monitor

This local, read-only dashboard separates sealed Farmer decision traces from
public decision reports submitted by assistants. It never infers all-chat
compliance from a saved instruction, a task title, or an old deployment proof.

Run `python monitor.py serve`, or `powershell -File start-monitor.ps1` on Windows,
then open <http://127.0.0.1:19467>. Python's standard library is sufficient.
The installer for this user copies this directory to
`C:\Arkmatx_Knowledge_Hub\future_branch_monitor`; its SQLite journal stays there
across source updates. The monitor observes Farmer at port 19466 every five
seconds. It cannot execute jobs, change LKG, resume quarantined work, or access
Farmer credentials. No public hosting or network binding is required.

The Farmer `/monitor` projection exposes scores, tiers, seal checks and aliased
candidates only on loopback. Job payloads, goals, inputs and credentials remain
behind existing authenticated endpoints. A health-only fallback is explicitly
labeled when a runtime has not yet received the projection.

The continuous-exploration panel reads the resident worker's signed frontier
checkpoint. It shows fresh, unique decision-policy fault-model checks separately
from real job outcomes. Execution can be idle while the explorer advances. The
monitor never schedules these cases: Farmer's own worker, watchdog and startup
service do that even when Codex and the dashboard are closed. A depleted modeled
frontier is labeled as watching for new state, not imaginary new computation.

## Public chat reports

Write a UTF-8 JSON file and run `python monitor.py record --file report.json`.
Only concise public actions and evidence references belong here, never secrets
or private reasoning. Example:

```json
{
  "schema": "aurum.future-branch.chat-check.v1",
  "thread_id": "actual-task-id",
  "operation_id": "build-monitor",
  "phase": "checking",
  "summary": "Validate the read-only monitor before starting it",
  "candidates": ["Run focused tests", "Hold installation"],
  "selected": "Run focused tests",
  "evidence": ["Projects/FutureBranchMonitor/test_monitor.py"],
  "recovery": "Keep the existing Farmer release and stop only the monitor"
}
```

Phases: `planned`, `checking`, `executing`, `checked`, `failed`, `waiting`.
Reports are deduplicated by semantic contents; timestamps do not refresh them.
All imported reports remain labeled self-reported even if their author writes
"verified". Evidence references are displayed, not executed or auto-approved.

`context --file tasks.json` accepts `{"tasks":[{"id":"...","title":"...",
"status":"active","kind":"codex"}]}` from the app's latest task inventory.
`bus --file events.json` accepts `{"events":[{"payload":{...}}]}` and imports
only the exact chat report schema. The task monitor heartbeat refreshes these
snapshots; it must not manufacture reports for other tasks. Task inventory is
stale after 10 minutes; reports are old after 30 minutes. An old or absent report
is a visibility gap, not proof that the assistant skipped decision checking.
These observation thresholds never authorize execution or failure retries.

The dashboard serves only `/` and `/api/status`, binds loopback and validates
Host headers. It offers no HTTP writes or CORS permission. It collects no raw
chat transcripts. All task/report strings are rendered with DOM textContent.

## Verification

Run `python -m unittest discover -s Projects/FutureBranchMonitor -v` from the
repository root, plus the Farmer tests for the redacted projection. Live
acceptance checks the installed runtime's seals and LKG flag after the existing
reversible Windows deployment and restart canary. Seed/GitHub sync and protected
LKG authority remain unchanged.
