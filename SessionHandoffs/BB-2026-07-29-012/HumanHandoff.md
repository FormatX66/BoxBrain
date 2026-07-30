# Human Handoff

## What was accomplished

- The operator approved the recommended scrolling capability as long as the
  work did not interfere with daytime computer use.
- Added explicit absolute X/Y coordinates to every scroll request.
- Limited scrolling to standard 120-unit wheel steps, at most ten combined
  vertical and horizontal steps per operation.
- Added strict controller validation, dashboard fields and validation, native
  canonical parsing, positive/negative wheel encoding, atomic move-plus-scroll
  delivery, installer provenance, Pi experiment-plan support, and focused
  tests.
- Passed 23 focused controller cases and 17 Pi-installer cases.
- Passed Python, PowerShell, JSON, Dart formatting, and Git diff checks.
- Pushed BrainConnect revision `494ec3f` to draft pull request 12.
- Did not run Flutter analysis/tests, Docker, native builds, the Pi, the VM,
  system services, or checkpoint operations.

## Decisions made

- Implement scrolling before shell or clipboard because it adds useful control
  with less target-data exposure.
- Never depend on the cursor's prior location. Move to explicit coordinates
  and scroll atomically in one pinned connection.
- Use standard 120-unit steps and cap the combined request at ten steps.
- Keep all resource-intensive and live verification in the nightshift queue.

See [DecisionLog.md](DecisionLog.md).

## Current blockers

- Native C warnings-as-errors builds have not run for this revision.
- Flutter analysis and widget tests have not run for this revision.
- The new artifact has not passed the Pi's exact FreeRDP 3.26 gate or a live
  independently observed scroll proof.

## Immediate next step

During nightshift, run the full local gates, exercise the real-Pi upgrade
preflight, cross-build and promote the artifact, then prove one scroll with
bounded before/after frames from `clean-linked-rotated-2026-07-29`.

## Long-term objective

Produce a repeatable AI computer-control workbench whose capabilities are
strictly bounded, independently observable, and safe to develop without
disrupting the operator's normal workstation use.
