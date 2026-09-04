# Aurum Farmer

Farmer turns an Aurum/BoxBrain request into one durable job and keeps advancing
it after a chat response, app session, runner process, or supervisor process
ends. The ledger, not conversation memory, is authoritative.

## Future Branch Decision Engine v1

### Continuous failure-path frontier

The resident supervisor now owns a separate, automatically supervised failure
explorer for its entire lifetime, including when no job is queued. It resumes a
signed SQLite checkpoint after process/host restart. A dead worker is replaced;
a worker that stops publishing progress is replaced after a bounded grace period.
An inherited lifetime pipe prevents orphan workers after the supervisor exits.
An exclusive lease prevents competing workers from advancing the same frontier.

The explorer tests novel combinations of authority, dependencies, risk and
reversibility boundaries, rollback/LKG availability, evidence tiers, expiration,
completed/quarantined state, attempts and parent dependencies against the actual
decision engine. It starts with baseline and single-factor checks, then traverses
interactions without replacement. Equivalent job IDs/payloads collapse into the
same observed policy shape. The built-in control has over four million distinct
modeled combinations; these are not claims about all possible real-world failures.

An independent oracle checks promotion, DAG structure, role separation and LKG.
The child imports no executors or configured external probes; it cannot run a
real job, modify its ledger state, promote LKG, or grant authority. Model findings
are separately sealed and the case cursor advances instead of replaying failures.
The resident supervisor holds new execution while the explorer is unavailable or
has unresolved invariant/model errors. A corrupt signed checkpoint is held until
its contents change, rather than retried unchanged. Existing job quarantine and
admission rules are not weakened.

Default batches use at most 16 cases and 0.15 CPU seconds, with fair four-case
slices per observed policy shape and a one-second yield. Observation and liveness
timestamps never count as new paths. If a modeled frontier is exhausted, the
service watches for new semantic state rather than fabricating work. Actual
engine outcomes and model predictions remain distinct in telemetry. Windows
startup/restart protection also permits bounded operation on battery; shutdown,
sleep, explicit stops and unavailable hardware are not promises of computation.
The service does not depend on a chat, dashboard, or Codex remaining open.

`GET /health` and `/monitor` expose `continuous_exploration`: worker/watchdog
health, signed path counts, recent model results, evidence age, recovery count,
and scope. The existing authenticated APIs continue to protect real job details.

Every ledger claim now passes the decision engine, including direct callers.
The supervisor explores active jobs while the selected executor runs. The
event-driven Farmer-v3 worker imports the same engine at its common dispatch
boundary and prepares pending Slush/Hive ingress concurrently.

The engine captures semantic inputs and evidence hashes, generates a bounded DAG
of candidate actions, success/degraded/failure/timeout/no-change/unexpected
outcomes, verification/recovery successors, a hold control, and protected LKG.
It prunes invalid dependencies/cycles, unavailable authority, expired, duplicate,
quarantined, unsafe, and nonpositive-value candidates. Submitted actions remain
the executable vocabulary; generated outcome nodes never acquire authority.

Scoring is `probability * expected benefit * measured evidence quality - failure
risk - irreversible cost - uncertainty`. Proposer-supplied evidence quality does
not establish verification. Near ties wait. Static, unit, VM, hardware-model,
and canary tiers must pass in order; unavailable tiers remain pending. Trusted
probes run in parallel on isolated resources and serially on exclusive resources.
Successive halving and per-cycle budgets allocate stronger candidates more work.

`decision` on a branch accepts `parents`, `required_tier`, `effect`,
`rollback_ref`, `expires_at`, `uncertainty`, `irreversible_cost`, `impossible`,
and `implementation_ref`. A declared state-changing effect requires an existing
LKG, rollback reference, at least unit verification, and a trusted probe receipt
confirming rollback verification. Risk above 0.35, reversibility below 0.9, or
any irreversible cost prevents automatic promotion. Existing authorization,
executor allowlists, device identity, seed, and Guardian gates still apply.

The runtime's restricted `future_branch` configuration owns resource budgets and
trusted probes. Jobs cannot supply probe commands or verifier identities. Probe
configuration accepts `tier`, `identity`, absolute-executable `argv`,
`timeout_seconds` (at most 60), and `resource` (`isolated` or an exclusive device
name). Probes receive a state/action digest on stdin in a disposable directory,
without ambient credentials or action payloads. They return JSON containing
`passed`, the same `input_digest`, and (for mutations) `rollback_verified`.
Probe receipts are retained by hash; adapters must retain the underlying evidence.
An administrator must review probe isolation, command behavior and hardware
identity/rollback safeguards before registration. A temporary directory alone
is not a security sandbox.

Default installations supply static verification and independent result checks;
they do not claim unavailable VM, hardware, or QPU coverage. Noop results are
recomputed independently and external receipt files are read back independently.
GitHub and Chat-to-Git results receive a separate readback of the same run/source.
A local-process LKG promotion requires a `verification_artifact` with a pinned
`path` and `sha256`; a zero exit code alone cannot promote its output to LKG.
Other legacy executors retain their evidence contracts and sovereign verification
paths; a generic signed receipt is not physical or hardware proof.

Read the durable DAG with `aurum-farmer futures --job JOB_ID` or authenticated
`GET /futures/JOB_ID`. `/health` includes engine identity, available tiers,
decision count, resolved outcome count and mean Brier score. Predictions are
recorded before execution and correlated with verified outcomes; waiting is not
scored as failure. Decision/outcome tables are append-only and hash-linked into
the existing signed event chain. Semantic state, engine source, or probe revision
changes invalidate cached verification. Heartbeats alone do not regenerate work.

The [Future Branch live monitor](../FutureBranchMonitor/README.md) displays
redacted sealed decision traces from loopback `GET /monitor`, plus separately
labeled public chat reports and missing-report visibility gaps. It is read-only
and does not turn saved instructions or self-reports into runtime proof.

The database migration is additive. Older releases, LKG, seed pins, sync logic,
signed evidence, and job retry rules are preserved. The versioned Windows
deployment verifies default-on decisions and calibration after restart. The
Farmer-v3 installer stages the canonical engine and includes it in rollback.

Coverage is all operations entering either Farmer runtime (including generic
GitHub and Chat-to-Git adapters). Direct OS commands and independently deployed
legacy controllers must enter a Farmer adapter to gain this coverage; installing
this runtime does not intercept every process on every device.

## State machine

```text
RECEIVED -> PLANNED -> READY -> RUNNING -> VERIFYING -> SUCCEEDED
                              |             |
                              |             +-> RETRYING / RECOVERING
                              +-> WAITING / BLOCKED_HUMAN / FAILED_FINAL
```

Every state change is validated and hash-chained. Evidence and event rows are
append-only. Every attempt receives an HMAC-sealed receipt; success additionally
requires every declared evidence kind to be present, verified, and sealed.

## Executors

- `github_workflow` dispatches and reads back a GitHub Actions run.
- `chat_to_git` sends one validated request through
  `FormatX66/Chat-to-Git-Pipeline`, then verifies the feedback issue, Actions
  result, and downloadable receipt artifact.
- `local_process` runs only an exact executable configured in the local
  allowlist, never a shell string.
- `evidence_file` waits for and hashes an external/physical receipt.
- `human_boundary` records a real human-only edge.
- `noop` is an internal end-to-end service canary.

If one branch fails, Farmer quarantines it and promotes the next warm safe
branch. Transient retries are bounded. A stable failure is replayed only after a
named state, evidence, implementation, environment, dependency, hypothesis, or
authority dimension changes.

## Local use

From the repository root:

```powershell
$env:PYTHONPATH = (Resolve-Path .\Projects\AurumFarmer).Path
python -m aurum_farmer --config .\work\farmer\farmer.json init --root .\work\farmer
python -m aurum_farmer --config .\work\farmer\farmer.json canary
python -m aurum_farmer --config .\work\farmer\farmer.json run --once
python -m aurum_farmer --config .\work\farmer\farmer.json status
```

Submit any job as a JSON object with a `goal` and complete `branches` array:

```powershell
python -m aurum_farmer --config .\work\farmer\farmer.json submit --file job.json
```

Route a bounded request through Chat-to-Git under Farmer:

```powershell
python -m aurum_farmer --config .\work\farmer\farmer.json `
  submit-chat-to-git --prompt "Check the repository status" `
  --dedupe-key "chat-to-git-status-current-main"
```

## Persistent Windows install

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\install-aurum-farmer.ps1
```

The installer creates an immutable versioned application release under the
current user's local application data, preserves all older releases, keeps the
ledger and signing material in a separate runtime directory, registers a
current-user `Aurum Farmer` scheduled task with restart-on-failure, starts it,
and verifies the loopback health endpoint. It does not expose a firewall port or
copy a provider credential.

The local API binds to `127.0.0.1:19466`. `/health` is public only on loopback;
job reads/writes require the bearer token stored in the ACL-restricted runtime
token file.

Unregister the task without deleting durable state:

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\uninstall-aurum-farmer.ps1
```

## Verification

Future Branch also guards every controller API request (after authentication)
and every Core worker dispatch. The shared `operation_gate.py` journal blocks
concurrent duplicate effects, unchanged failed operations and unresolved crashed
attempts across restarts. Request IDs and receipt-only updates cannot unlock a
failure. Read-only observations and emergency stop remain reachable. Core plans
can select a fallback after a quarantined primary without reexecuting it.

Farmer's signed ledger preserves operation quarantine across new job IDs. Its
health telemetry reports `cross_job_quarantine`, `execution_revision` and the
quarantine count. The existing bounded transient retry policy remains; once its
budget is exhausted, resubmitting an equivalent job does not reset that budget.
Resume updates only the named authority/dependency dimension.

Controller admission is not independent effect verification: a 2xx response is
recorded as observed, never verified completion or LKG promotion. Existing
executor permissions, approvals, idempotency, result verification and LKG gates
remain authoritative. Git source/configuration contents are observed where
available; remote hardware/environment changes require adapter-specific evidence.
Code outside these dispatchers must follow the repository's state-first/Future
Branch policy; this integration does not intercept arbitrary shell commands.

```powershell
$env:PYTHONPATH = (Resolve-Path .\Projects\AurumFarmer).Path
python -m unittest discover -s .\Projects\AurumFarmer\tests -v
```

The suite covers restart/resume, expired-runner recovery, bounded retries,
human boundaries, evidence-gated completion, LKG preservation, branch ranking,
deduplication, append-only storage, and the Chat-to-Git adapter contract.
