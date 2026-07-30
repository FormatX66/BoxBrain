# Human Handoff

## What was accomplished

- Added a read-only BrainConnect upgrade check that runs before building a
  controller package, uploading files, or changing the Pi service.
- The check blocks an enabled RDP execution setting even when the controller
  is stopped.
- A running controller must prove, through its private authenticated health
  endpoint, that execution is disabled, production health is good, and the
  emergency stop is armed.
- Added focused tests for enabled and disabled settings, quoted systemd
  settings, safe and unsafe health, and installer ordering.
- Passed 16 quick Pi-installer tests, parsed the PowerShell installer without
  errors, and compiled the new Python preflight.
- Pushed BrainConnect revision `be0738c` to draft pull request 12.
- Split the remaining work into low-impact daytime decisions and a
  resource-intensive nightshift queue. No Pi, VM, Docker, Flutter, or service
  operation was run.

## Decisions made

- Trust neither configuration nor live health alone: both must agree that an
  installed controller is inert before upgrade.
- Keep daytime work limited to quick local edits, documentation, tests, and
  operator decisions.
- Reserve Pi promotion, VM restore/live proof, Flutter verification, and
  cross-architecture native builds for nightshift.
- Retain the retired checkpoint unless deletion and Hyper-V merge effects
  receive explicit approval.

See [DecisionLog.md](DecisionLog.md).

## Current blockers

- The new preflight has not yet been exercised against the real Pi.
- The operator still needs to confirm scrolling, shell, or clipboard as the
  next native capability. Scrolling is the recommended low-exposure choice.
- FreeRDP 3.15 build versus Pi 3.26 runtime remains an explicit compatibility
  boundary.

## Immediate next step

Confirm the next native capability during daytime. At nightshift, run the
ordered verification queue beginning with the real-Pi preflight dry run.

## Long-term objective

Produce a repeatable AI computer-control workbench that independently verifies
every action against an exact disposable target while protecting daytime
system responsiveness.
