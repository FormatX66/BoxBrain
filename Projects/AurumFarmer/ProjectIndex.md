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

## Operational state authority

Farmer's validating SQLite WAL ledger plus its local signing key is the
**production local operational-state authority on Farmer-controlled nodes**.
The generic `data/aurum/runtime-checkpoint.json` is not a second writable
scheduler authority there; it is a compatibility/reconstruction projection.
This avoids split-brain between two local state stores.

The local-state order is:

1. validating Farmer ledger/event chain/signing material;
2. a zero-authority compatibility checkpoint derived from Farmer;
3. the generic runtime checkpoint only on nodes where Farmer is not the active
   controller.

`Admin/checkpoint_farmer_runtime.py` performs that fail-closed projection. It
requires the existing ledger and signing key, verifies the Farmer event chain,
maps Farmer job states into the generic checkpoint vocabulary, and refuses to
copy destructive authority, candidate promotion, or LKG mutation permission.
The generic reconstruction/resume tooling therefore remains useful without
creating a peer authority.

This architecture is the production resolution of the state-authority frontier
tracked in Aurum issue #40.

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
- `../../Admin/checkpoint_farmer_runtime.py` — Farmer-to-generic zero-authority
  compatibility projection

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
8. A Farmer-derived generic checkpoint is a projection/cache, never a peer
   writable authority and never an authorization token.

## Related architecture

- [State-first execution logic](../../Architecture/ExecutionLogic.md)
- [Future Branch current workflow](../../Architecture/FutureBranchCurrent.md)
- [Future Branch execution gate](../../Architecture/FutureBranchExecutionGate.md)
- [Execution routes](../../Architecture/ExecutionRoutes.md)
- [Aurum state authority](../Aurum/STATE_AUTHORITY.md)
- [Aurum project](../Aurum/ProjectIndex.md)
