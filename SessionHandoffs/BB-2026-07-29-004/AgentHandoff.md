# Agent Handoff

## Current Objective

Implement the first disabled-by-default, out-of-process control adapter for the
exact disposable Windows VM without expanding authority to the Raspberry Pi,
operator workstation, or any other target.

## Tasks

1. Define a versioned request/result protocol for all eight queued operation
   kinds.
2. Add bounded operation state transitions from `queued` to `running` and one
   terminal state.
3. Recheck emergency stop, task state, enabled target identity, endpoint, and
   pinned certificate immediately before execution.
4. Define an external credential provider that never exposes secrets through
   Git, the API, command arguments, logs, or audit payloads.
5. Implement one-operation-at-a-time dispatch with a disabled default.
6. Record bounded results, timing, failure class, and before/after evidence.
7. Prove shell, keyboard, pointer, and clipboard operations independently in
   deterministic tests before the live VM.
8. Run one controlled live operation, classify the result, then restore and
   verify checkpoint `clean-linked-2026-07-29`.

## Dependencies

- BrainConnect revision `155b526`
- BrainConnect draft pull request
  [8](https://github.com/FormatX66/BrainConnect/pull/8)
- Parent identity branch `feature/brainconnect-pi-rdp-live-lab`
- Pi controller at `10.12.194.1:8000`
- Enabled disposable Windows target at `10.12.194.9:3389`
- Clean Standard checkpoint `clean-linked-2026-07-29`
- Canonical contract:
  [BrainConnect open-lab control](../../../BrainConnect/docs/OPEN_LAB.md)

## Files affected

- BrainConnect controller models, database, API, tests, and documentation
- BrainConnect Flutter operation forms, API client, status model, and tests
- BrainConnect `plugins/open-lab-control/`
- BoxBrain admin, architecture, project, and session indexes
- BoxBrain `SessionHandoffs/BB-2026-07-29-004/`

## Required repositories

- `https://github.com/FormatX66/BrainConnect`
- `https://github.com/FormatX66/BoxBrain`

## Verification checklist

- Adapter cannot address the Pi, workstation, or an unregistered target.
- Target UUID, endpoint, and pinned certificate are rechecked before execution.
- Emergency stop prevents transition to `running`.
- Only active `open` tasks can execute operations.
- Credentials never appear in repository files, API bodies, arguments, logs,
  audit events, or test fixtures.
- Every protocol field and result has a hard size or time limit.
- Command and clipboard contents remain excluded from audit events.
- A failure leaves a truthful terminal state and bounded diagnostic category.
- No retry can exceed its action or task budget.
- The clean checkpoint is restored and verified after the first live run.
- BrainConnect and BoxBrain validation remain green.

## Suggested commit message

`feat: add disabled VM control adapter`

## Suggested branch

`feature/brainconnect-open-lab-adapter`

## Potential risks

- RDP control normally requires a live authenticated desktop session.
- A transport bug could send input to the wrong session unless endpoint,
  certificate, and session correlation are verified together.
- Shell and clipboard payloads can contain secrets even when the audit log
  stores only hashes.
- Pointer coordinates can become invalid when resolution or scaling changes.
- Key chords can leave modifiers pressed if interruption is not handled.
- An interrupted `running` operation needs deterministic recovery.
- Snapshot restore can rotate the RDP certificate and disable the target.

## Estimated completion order

1. Versioned adapter protocol and failure taxonomy
2. Transactional operation state machine
3. External credential-provider contract
4. Deterministic fake adapter and controller tests
5. Disabled real RDP adapter skeleton
6. One-operation shell and input verification
7. Bounded evidence and dashboard result display
8. Controlled live VM run
9. Checkpoint restoration and handoff
