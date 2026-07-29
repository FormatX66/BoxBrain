# Human Handoff

## What was accomplished

- Diagnosed the Windows RDP session using read-only process and Terminal
  Services evidence.
- Confirmed successful authentication as the target-local `boxbrain-lab`
  account and reconnection to the existing desktop session.
- Updated the BrainConnect connector to:
  - enable interactive auto-logon only after exact certificate and credential
    checks;
  - request the existing console session;
  - force reliable slow-path input; and
  - reject suspended input instead of reporting a no-op success.
- Accepted an optional Windows UTF-8 byte-order marker in local experiment
  plans while retaining strict JSON validation.
- Passed all six native tests for amd64 and arm64 and all seven Pi experiment
  runner tests.
- Installed BrainConnect revision `871fe43` on the Pi with control SHA-256
  `592feb4b12fb5c7a6066cae6433495ecbc050647ebff90a0ea4d26ec19c3432d`.
- Independently verified keyboard control: `Ctrl+Shift+Esc` launched Task
  Manager and a Windows-key plus Unicode sequence launched Notepad.
- Disabled execution, removed the systemd execution drop-in, encrypted target
  credentials, and temporary runners, then restored the exact clean VM
  checkpoint.

## Decisions made

- Bind the local RDP credential to machine domain `BB-WIN-LAB`, reconnect the
  console session, and use slow-path input for the headless client.
- Keep process evidence separate from transport success; application presence
  proves launch, but not cursor position or correct text contents.
- Do not add credential keystrokes, weaken Windows policy, or rely on longer
  timing after the evidence identified the actual transport issue.

See [DecisionLog.md](DecisionLog.md).

## Current blockers

- Cursor position, pointer-button effects, and text contents are not
  independently visible because frame observation is not implemented.
- Shell, pointer-button, scroll, and clipboard execution are not implemented
  at the native connector boundary.
- The reproducible build uses FreeRDP 3.15.x while the Pi runtime is FreeRDP
  3.26.0; current on-host tests pass, but the compatibility boundary should be
  aligned or made explicit.

## Immediate next step

Add bounded, redacted frame observation and use it to verify a pointer move and
the visible result of a keyboard sequence. In parallel, align the native build
baseline with the Pi runtime or add an explicit compatibility gate.

## Long-term objective

Produce repeatable, independently verified mouse-and-keyboard control of an
exact, disposable target while keeping credentials ephemeral, actions audited,
and checkpoint recovery deterministic.
