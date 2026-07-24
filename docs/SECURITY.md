# Security and Lab Boundaries

BoxBrain is intended for machines and accounts the operator owns or is
explicitly authorized to test. Initial executor development belongs in a
disposable VM or physically isolated lab target.

## Invariants

These remain active in every policy profile:

- Target allowlisting and visible target identity
- Immutable action and policy-decision logging
- A local emergency stop independent of the planner
- Secret redaction before model requests and logs
- Capability-scoped, out-of-process plugins
- No controller self-update during an active run
- No hidden persistence or privilege escalation

## Durable audit boundary

Task creation and its audit event are committed atomically. The event table has
no mutation API, and SQLite triggers reject direct updates or deletions. Runtime
data stays under `controller/data/` and is excluded from source control.

## Read-only Windows Sandbox observer

The alpha observer captures only the visible Windows Sandbox window pixels. It
exposes target identity and PNG frames, but no keyboard, mouse, clipboard,
file, process, or shell operation. Frame responses are local-only and marked
`no-store`.

The supplied `sandbox/BoxBrain-Isolated.wsb` profile disables networking,
clipboard, audio/video input, printer redirection, and vGPU, and enables
Protected Client mode. Closing the Sandbox discards its contents.

`research` and `open` may reduce per-action confirmations, but they do not
remove containment, logging, identity, or emergency-stop controls.

## Before adding an executor

- Use a VM snapshot with no sensitive files or credentials.
- Put the target on a dedicated network segment with explicit egress rules.
- Require mutual authentication between UI, controller, and plugins.
- Store provider credentials outside the repository and encrypt them at rest.
- Sign plugin packages and verify their hashes before activation.
- Define maximum task time, action count, cost, and data-transfer limits.
- Make restoration and evidence export part of the normal run lifecycle.

## Self-improvement boundary

BoxBrain may propose changes in a branch, run tests in a build sandbox, and
produce a review packet. It must not replace its running controller or merge its
own changes during an active session.

