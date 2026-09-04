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

The dashboard serves only `/`, `/activity.js`, `/api/status` and `/api/activity`, binds loopback and validates
Host headers. It offers no HTTP writes or CORS permission. It collects no raw
chat transcripts. All task/report strings are rendered with DOM textContent.

## Verification

Run `python -m unittest discover -s Projects/FutureBranchMonitor -v` from the
repository root, plus the Farmer tests for the redacted projection. Live
acceptance checks the installed runtime's seals and LKG flag after the existing
reversible Windows deployment and restart canary. Seed/GitHub sync and protected
LKG authority remain unchanged.

## Unified workload activity

The existing dashboard includes a searchable, paginated local/GitHub workload
table, source health, CPU/RAM where observed, current steps, elapsed times and
provider links. It never adds remote memory to local RAM, infers job ownership
from a process name, or interprets low CPU as permission to close a process.

`workloads.py` uses standard-library read-only Windows process APIs (or `/proc`
on Linux), samples every three seconds, and identifies processes by PID plus
creation time. CPU is the process CPU-time delta divided by elapsed time and
the host's logical CPU count. The initial CPU sample and inaccessible metrics
are unavailable, not zero. RAM is working set/RSS; shared pages may overlap.
An ended process remains visible for 30 seconds with unavailable current metrics.
Raw command lines, executable paths, credentials and transcripts are not collected.

GitHub reads use the existing signed-in `gh` CLI with a fixed github.com host,
repository and read-only Actions API paths. It observes the newest 20 BoxBrain
runs and fetches jobs for up to four prioritized runs (100 jobs per run max).
There is no claim of full-account coverage. Details for completed attempts are
cached without refreshing their evidence timestamps. Poll delay is 30 seconds
with active work, 60 seconds when idle, plus request time. Requests are serial,
bounded and back off on failures and provider rate limits. A run-level fallback
has unconfirmed runner location until actual runner evidence exists. GitHub job
API CPU and RAM are unavailable without job instrumentation. The saved Codex
cloud environment appears as a capability gap/link, never as an active process.

Provider observations retain source timestamps on errors. Local samples expire
after 10 seconds, GitHub after 90. Empty, stale, disconnected and provider-error
states are distinct. The browser refreshes every three seconds and explicitly
marks retained values historical if the dashboard disconnects. Collector wall
time and monitor CPU time are reported separately; the latter excludes gh child
CPU and is not a total system overhead measurement.

The summary-only `/api/activity` contract is `aurum.workload-activity.v1`, with
`read_only=true`, `authority_granted=false`, provider timestamps, summary and a
snapshot ID. Refreshing the browser does not create a new snapshot ID. Farmer's
`ActivityReader` reads only this fixed loopback endpoint, refuses redirects,
limits response size and waits at most 250 ms, at most once per three seconds.
The independent host sensor remains authoritative. A fresh observed process
using at least 25% of the host CPU can reduce the explorer budget only if the
host sensor also sees at least 50% CPU for three successive samples. Existing
critical-pressure rules and five-clear-sample recovery remain in force. Cloud
activity is advisory and does not change local CPU or RAM. The signed frontier
records the exact consumed snapshot ID, local observation time, selected budget
and contention flag. If the dashboard is absent, the existing host-only budget
continues; it does not stop the resident explorer or authorize external actions.

Links open actual GitHub job/run pages. Cancel/re-run availability is determined
by the user's provider permissions and current run state. The monitor has no
kill, shell, pause, dispatch or write endpoint. It cannot migrate a live process
or close/reopen applications. A managed cloud workload API is not connected.

Source contracts: [GitHub workflow jobs](https://docs.github.com/en/rest/actions/workflow-jobs)
and [API polling/rate-limit guidance](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api).
