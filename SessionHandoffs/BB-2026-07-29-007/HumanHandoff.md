# Human Handoff

## What was accomplished

- Extended BrainConnect's native FreeRDP connector from pointer movement to
  bounded Unicode text and fixed allowlisted key or chord input.
- Added a guarded Pi workflow that installs the artifact disabled, streams a
  DPAPI-protected Windows credential into host-encrypted systemd credentials,
  enables only a reviewed bounded run, and removes the execution configuration
  and credentials afterward.
- Installed revision `fd2281e` on the Pi with control SHA-256
  `1d91cf630e7b1f16f8c95bc871479218caa86a1e9d7d9aa8aa3aebdbaa59b74b`.
- Passed the Pi's FreeRDP 3.26 identity, credential, and native control
  fixtures.
- Sent one successful pointer operation and multiple successful key and text
  operations through the exact certificate-pinned RDP session.
- Checked the Windows guest independently through its restricted Pi-only link.
  The expected Notepad, Task Manager, and Settings processes were not present,
  so the run proves transport-level event submission but not a durable visual
  UI change.
- Returned the Pi to its safe idle state: the controller is healthy,
  `executor_enabled=false`, the execution drop-in is absent, and encrypted RDP
  credential count is zero.
- Published BrainConnect commit `e81f5f5` in draft pull request 11.

## Decisions made

- Accept systemd's root-owned, root-group `0440` runtime credential files only
  when a named service-account ACL grants read access and no unsafe group,
  world, symlink, owner, or directory condition exists.
- Keep successful operation semantics limited to exact-session authentication
  and FreeRDP event submission until an independent verifier confirms the
  expected target-state change.
- Retain the reviewed native binary on the Pi in an inert state while removing
  the execution drop-in and all encrypted target credentials after each run.
- Add only the left Windows key to the fixed key allowlist; right Windows and
  menu keys remain unavailable.

## Current blockers

- Independent visual or guest-state proof is still missing for mouse and
  keyboard actions.
- Each operation currently creates and closes its own RDP session, so transient
  menus or dialogs may not survive across a multi-operation task.
- The current Windows account lacks Hyper-V authority to restore checkpoint
  `clean-linked-2026-07-29`. BrainConnect's Pi-side rollback is complete, but
  host checkpoint restoration remains pending.
- Shell, pointer buttons, scrolling, clipboard, and frame observation remain
  unavailable at the native boundary.

## Immediate next step

Implement one bounded persistent RDP input sequence with an independent frame
or guest-state verifier, then repeat a harmless single-session keyboard or
pointer experiment. Restore the clean checkpoint with an authorized Hyper-V
account before that run and re-probe the target certificate afterward.

## Long-term objective

Run repeatable, independently verified computer-use experiments against the
exact disposable Windows VM while keeping credentials ephemeral, every action
audited, and the Pi controller inert between experiments.
