# Aurum Farmer Project Index

## Purpose

Aurum Farmer is the persistent orchestration control plane for Aurum and
BoxBrain. It owns durable goals, Future Branch scheduling, execution leases,
verification, recovery, Last Known Good lineage, and human-boundary handoff.
Chat, voice, GitHub Actions, Chat-to-Git, local reviewed processes, and physical
receipt watchers are clients or executors beneath Farmer; none is the durable
controller.

## Current status

Farmer v1 is implemented as a standard-library Python runtime with a SQLite WAL
ledger, explicit job state machine, append-only signed evidence/event records,
single-leader supervisor lease, runner watchdog, bounded retry classification,
branch quarantine, LKG promotion, a loopback authenticated API, and Windows and
Linux service installers.

Hosted Windows installation is now CI-proven. GitHub Actions run `32878837340`
on source commit `da4239ab301c5fb2d6748145dae75b03e3589bed` successfully exercised the
real Windows installer, persisted a matching source/health receipt, registered
and started the `Aurum Farmer` scheduled task, verified the authenticated
loopback health endpoint and event chain, then removed the ephemeral CI task
through the real uninstaller. This is **installer/service-contract proof on a
hosted Windows machine**, not evidence that Farmer is already installed and
running on the operator's long-lived physical computer. Live deployed-runtime
proof remains a separate boundary.

## Canonical implementation

- [Runtime and operator guide](README.md)
- `aurum_farmer/ledger.py` — durable ledger, state machine, evidence, receipts,
  recovery, and LKG records
- `aurum_farmer/supervisor.py` — persistent leader, watchdog, and continuation
- `aurum_farmer/executors.py` — reviewed executor adapters
- `aurum_farmer/api.py` — loopback control surface
- `tests/test_farmer.py` — restart, recovery, retry, evidence, LKG, boundary,
  scheduler, dedupe, and Chat-to-Git adapter regression proof
- `installer/install-aurum-farmer.ps1` — current-user Windows service install
- `installer/aurum-farmer.service` — Linux/Pi systemd unit template
- `.github/workflows/aurum-farmer-ci.yml` — Linux runtime regression plus hosted
  Windows install/start/health/uninstall proof

## Invariants

1. Conversation completion is never job completion.
2. Only a signed Farmer receipt plus every branch evidence requirement can close
   a job.
3. Expired runner leases enter `RECOVERING`; they do not disappear.
4. A stable unchanged failure is quarantined instead of blindly replayed.
5. Last Known Good changes only after verified success.
6. Human blocking is limited to an explicit credential, destructive or
   irreversible authorization, physical action, identity check, or subjective
   decision.
7. Chat-to-Git is the `chat_to_git` executor. GitHub workflows are the
   `github_workflow` executor. Farmer remains the state authority.

## Related architecture

- [State-first execution logic](../../Architecture/ExecutionLogic.md)
- [Future Branch current workflow](../../Architecture/FutureBranchCurrent.md)
- [Future Branch execution gate](../../Architecture/FutureBranchExecutionGate.md)
- [Execution routes](../../Architecture/ExecutionRoutes.md)
- [Aurum project](../Aurum/ProjectIndex.md)
