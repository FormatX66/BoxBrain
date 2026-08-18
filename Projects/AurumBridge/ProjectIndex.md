# Aurum Bridge Project Index

## Purpose

Aurum Bridge is the bounded control/evidence path between Aurum/ChatGPT and authorized physical Windows machines. It exposes explicit capabilities rather than an unrestricted remote shell.

## Current status

Active bootstrap subsystem. The Windows self-hosted runner is elevated for privileged bounded operations; reasoning and usage paths are being moved local-first so metered external reasoning is an escalation rather than the default.

## Canonical documents and evidence

- [Bridge contract and current capabilities](README.md)
- `AurumBridge.ps1` — bounded PC capability executor
- `AurumLocalReasoner.ps1` — local reasoning runtime adapter with provenance
- `UsageLoop.ps1` — usage incident detector/evidence loop
- `jobs/` and `results/` — bounded PC jobs and returned evidence
- `reasoning-jobs/` and `reasoning-results/` — attributed reasoning requests/results
- `usage-events/` and `usage-results/` — usage incident evidence

## Process invariants

- Expected waiting/refusal states do not become false failures.
- Every reasoning result identifies the processor/runtime/provider and whether external provider usage was consumed.
- Local evidence must be recoverable even if source-repository publication fails.
- Destructive capabilities remain separately gated and evidenced.
