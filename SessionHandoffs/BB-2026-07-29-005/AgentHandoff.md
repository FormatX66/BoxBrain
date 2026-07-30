# Agent Handoff

## Current Objective

Implement the first live VM connector behind BrainConnect's proven open-lab
adapter protocol without changing the controller API or broadening authority
outside the exact enabled Windows VM.

## Tasks

1. Choose and document the external runtime credential provider.
2. Extend a pinned FreeRDP 3.x out-of-process executable to authenticate only
   after exact certificate verification.
3. Correlate target UUID, endpoint, certificate, authenticated account, and
   interactive desktop session.
4. Implement one operation kind first with hard timeout and cancellation.
5. Add modifier cleanup and coordinate normalization before broader keyboard
   and pointer support.
6. Add bounded before/after evidence and result verification.
7. Implement clipboard redirection without drive, file, printer, device,
   audio, or camera redirection.
8. Decide whether shell uses UI typing, the existing Pi-only SSH boundary, or a
   separate guest agent while preserving one operation result contract.
9. Run a controlled live action and restore checkpoint
   `clean-linked-2026-07-29`.

## Dependencies

- BrainConnect revision `310c264`
- BrainConnect draft pull request
  [9](https://github.com/FormatX66/BrainConnect/pull/9)
- Open-lab queue branch and draft pull request 8
- Enabled Windows target at `10.12.194.9:3389`
- Pi controller at `10.12.194.1:8000`
- Existing FreeRDP 3.26 runtime and certificate helper on the Pi
- Clean Standard checkpoint `clean-linked-2026-07-29`
- [Adapter protocol](https://github.com/FormatX66/BrainConnect/blob/main/plugins/open-lab-control/PROTOCOL.md)

## Files affected

- BrainConnect controller adapter, service, persistence, API, and tests
- BrainConnect packaged deterministic fixture
- BrainConnect Flutter operation models, service, dashboard, and tests
- BrainConnect open-lab architecture, security, product, and protocol docs
- BoxBrain admin, architecture, project, and session indexes
- BoxBrain `SessionHandoffs/BB-2026-07-29-005/`

## Required repositories

- `https://github.com/FormatX66/BrainConnect`
- `https://github.com/FormatX66/BoxBrain`

## Verification checklist

- Credential provider exposes no secret through arguments, environment,
  controller state, logs, or audit events.
- Certificate mismatch disables the target before authentication.
- Session identity matches the requested target and lab account.
- Emergency stop and target disablement prevent a new claim.
- Timeout terminates the adapter and produces a failed operation.
- Controller restart recovers abandoned running work.
- Input cannot reach the Pi, workstation, or another desktop session.
- Key modifiers are released after success, failure, timeout, or interruption.
- Pointer coordinates are normalized to observed desktop dimensions.
- Raw output and clipboard content remain transient.
- The clean checkpoint is restored after the live run.

## Suggested commit message

`feat: add live FreeRDP control connector`

## Suggested branch

`feature/brainconnect-freerdp-control`

## Potential risks

- RDP authentication and interactive-session selection can target an
  unexpected session unless correlated explicitly.
- FreeRDP input and clipboard APIs may require an active event loop and channel
  lifecycle beyond the one-shot process protocol.
- Shell through UI typing is fragile; shell through SSH creates a second
  identity and authority boundary.
- Clipboard content may contain secrets even though BrainConnect does not
  persist it.
- A checkpoint restore may rotate the RDP certificate and disable the target.

## Estimated completion order

1. Credential-provider contract
2. FreeRDP authenticated session skeleton
3. Exact target/session correlation
4. One pointer or key operation
5. Timeout, interruption, and cleanup tests
6. Before/after verification
7. Remaining pointer and keyboard operations
8. Clipboard channel
9. Shell transport
10. Controlled live run and checkpoint restore
