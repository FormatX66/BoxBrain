# Human Handoff

## What was accomplished

- Changed the active BrainConnect experiment from observation-first to
  capability-first control inside the disposable Windows VM.
- Added a durable queue for eight bounded operation types: shell, typed text,
  key chords, pointer movement, pointer buttons, pointer scrolling, clipboard
  read, and clipboard write.
- Limited operation admission to active `open` tasks on the exact enabled
  target.
- Kept the emergency stop, 500-operation task limit, 300-second shell timeout,
  append-only audit, target identity, and clean checkpoint as outer controls.
- Prevented command and clipboard content from being copied into audit events;
  the audit records only type, size, and SHA-256 digest.
- Added Flutter forms for every operation and dashboard counts for queued
  tasks and operations.
- Added a disabled open-lab control plugin contract. No operation is executed
  yet and the controller still reports `executor_enabled = false`.
- Published BrainConnect revision `155b526` to draft pull request 8.

## Decisions made

- Start broad inside the exact disposable VM and work backwards from observed
  failures rather than preemptively disabling individual target-local
  capabilities.
- Do not remove the outer experiment boundary: exact target identity, audit,
  emergency stop, hard limits, external credentials, and checkpoint recovery
  remain mandatory.
- Keep durable queueing separate from live execution so the dashboard never
  reports an action as completed before an adapter returns verified evidence.

## Current blockers

- The open-lab control plugin has no executable adapter and remains disabled.
- RDP session credentials still need an external runtime provider; they cannot
  enter Git, target records, operation payloads, command arguments, or audit
  events.
- Operation result states and before/after evidence are not implemented.
- The first live experiment must include checkpoint restoration verification.
- Observation-only frame transport remains a separate pending track.

## Immediate next step

Implement an out-of-process VM-only adapter that accepts one queued operation,
connects only to the enabled target through an external credential provider,
returns a bounded result, and leaves the operation queued when any identity,
credential, transport, timeout, or verification gate fails.

## Long-term objective

Run repeatable, fully audited AI-control experiments on a resettable Windows
VM, discover actual failure modes from evidence, and progressively tighten only
the capabilities and parameters that cause problems.
