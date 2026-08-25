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

The Windows installer/service contract is CI-proven on hosted Windows, including
the checksum-pinned release-local Python fallback used when no suitable system
Python exists.

A real persistent self-hosted Windows deployment is now also proven on runner
`AURUM-LAPTOP-EBD8CG8P`. GitHub Actions run `32887137300`, pinned to source
commit `fd243eb4da45b19f413ffe055c71202e20fa92ca`, installed Farmer under the
actual `NT AUTHORITY\SYSTEM` service identity with a startup scheduled task and
the release-local embedded Python runtime. Initial loopback health passed. The
workflow then stopped the supervisor, queued durable canary job
`AF-0900243f0605488ca58e`, restarted the scheduled task, allowed the prior
90-second single-leader lease to expire, and verified that the restarted
supervisor recovered the same job to `SUCCEEDED` with a sealed receipt. Final
loopback health and the event chain both passed, the task remained `Running`,
and previous releases were preserved. The durable proof is
`Deploy/latest-windows-runtime-proof.json`.

This is deployed process-boundary restart/resume evidence for Farmer. It does
not infer destructive authority, LKG mutation, Tiny Seed physical boot proof, or
any unrelated physical proof.

## Canonical implementation

- [Runtime and operator guide](README.md)
- `aurum_farmer/ledger.py` — durable ledger, state machine, evidence, receipts,
  recovery, and LKG records
- `aurum_farmer/supervisor.py` — persistent leader, watchdog, and continuation
- `aurum_farmer/executors.py` — reviewed executor adapters
- `aurum_farmer/api.py` — loopback control surface
- `tests/test_farmer.py` — restart, recovery, retry, evidence, LKG, boundary,
  scheduler, dedupe, and Chat-to-Git adapter regression proof
- `installer/install-aurum-farmer.ps1` — Windows install supporting interactive
  users and service-hosted/system runners, with a checksum-pinned release-local
  Python fallback
- `installer/aurum-farmer.service` — Linux/Pi systemd unit template
- `.github/workflows/aurum-farmer-ci.yml` — Linux runtime regression plus hosted
  Windows install/start/health/uninstall proof
- `.github/workflows/aurum-farmer-self-hosted-windows-deploy.yml` — reversible
  deployed Windows install plus abrupt process-boundary restart/resume proof

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
