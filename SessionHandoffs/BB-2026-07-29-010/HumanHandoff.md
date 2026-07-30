# Human Handoff

## What was accomplished

- Added bounded, memory-only RDP frame observation and validated region,
  cursor, PPM, Base64, byte length, and pixel hash fields.
- Corrected the native connector to keep FreeRDP diagnostics off its JSON
  result channel, establish the standard target-user session, and wait ten
  seconds for the desktop to become input-ready.
- Added coordinate-bound pointer-button operations. Each button event includes
  absolute X/Y and performs its move and button action atomically in one RDP
  connection.
- Passed 67 controller tests, 8 Pi-runner tests, 11 Flutter tests with a clean
  analysis, and all 7 native tests for both amd64 and arm64.
- Installed BrainConnect revision `567ffa3` on the Pi. The native control
  SHA-256 is
  `090929ac598855b5da72732a08975a291fa84d4cfbb718585665c8c747c5077e`.
- Independently proved:
  - Notepad was running after keyboard control;
  - visible Notepad text was present in bounded frames; and
  - an absolute click placed the caret before a later independent keyboard
    operation inserted `|CLICK|`, producing visible
    `FINAL |CLICK|BoxBrain`.
- Rotated and verified the disposable lab credential after a diagnostic
  command exposed its previous value in local tool output. No credential value
  was written to either repository.
- Disabled execution, removed all encrypted RDP credentials, removed the
  systemd drop-in and all temporary Pi runners/binaries, and verified
  `executor_enabled=false`.
- Created and restored Standard checkpoint
  `clean-linked-rotated-2026-07-29`, ID
  `fd314c39-c3a7-418a-849c-02a9cb6fe982`. A final unauthenticated probe matched
  the pinned certificate.

## Decisions made

- Keep frame previews caller-bounded to 160-by-90 pixels and memory-only.
- Establish the standard target-user session and service a ten-second
  readiness window before observation or input.
- Keep native protocol JSON isolated on standard output; FreeRDP diagnostics
  use standard error.
- Require absolute coordinates on every pointer-button request.
- Retire the older checkpoint after credential rotation; do not delete or
  merge it without separate operator approval.

See [DecisionLog.md](DecisionLog.md).

## Current blockers

- The controller installer assumes execution is disabled during promotion. It
  installed revision `567ffa3`, but its final false-state check failed because
  the reviewed live execution drop-in was still enabled. Future upgrades need
  a preflight that refuses this state.
- The reproducible image builds against FreeRDP 3.15 while the Pi runs 3.26;
  the exact on-host gates pass, but the compatibility boundary remains split.
- Shell, pointer scrolling, and clipboard are still queue-only capabilities.
- The retired checkpoint still contains the old credential state. Removing or
  merging it is intentionally awaiting explicit approval.

## Immediate next step

Add a fail-closed controller-upgrade preflight that refuses promotion while
the live executor drop-in is enabled. Then select shell, scrolling, or
clipboard as the next native operation.

## Long-term objective

Produce a repeatable AI computer-control workbench that independently verifies
every action against an exact disposable target, keeps credentials ephemeral,
and restores a known clean state after each run.
