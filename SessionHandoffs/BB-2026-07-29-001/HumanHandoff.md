# Human Handoff

## What was accomplished

- Tested Windows Sandbox as a disposable RDP target and stopped safely when
  its own remote-session service could not expose a second RDP listener.
- Added a protocol-faithful RDP/NLA certificate fixture on Raspberry Pi
  loopback with no credentials, authentication, desktop, or application data.
- Found that the controller's minimal helper environment removed `HOME`, which
  FreeRDP requires before opening a network socket.
- Preserved only `HOME` in the fixed helper environment and added a regression
  test proving API credentials remain excluded.
- Added exact-match, certificate-rotation, mismatch-disablement, unreachable,
  and timeout live verification through the production controller and native
  helper.
- Made Pi upgrades stop and disable the earlier service before foreground
  verification and re-enable it only after the gate passes.
- Deployed and verified BrainConnect revision
  `1df9de72805c01f1a10908424096d1fcaf0bda40`.
- Published draft BrainConnect pull request
  [7](https://github.com/FormatX66/BrainConnect/pull/7).

## Decisions made

- Treat the Pi-loopback fixture as the live certificate-identity boundary test,
  not as a substitute for a full disposable desktop target.
- Preserve `HOME` as the only newly allowlisted helper environment variable;
  do not inherit the controller token or the full service environment.
- Make upgrade verification fail-safe by leaving the service disabled if its
  foreground gate fails.

## Current blockers

- A disposable full Windows VM or dedicated lab machine has not been selected
  for frame transport and later desktop testing.
- Windows Sandbox cannot host the required second RDP listener on this system.
- A controlled dashboard credential-provisioning workflow is still required;
  the long-lived Pi token remains on the Pi.
- BrainConnect pull request 7 is stacked on pull requests 6 through 1 and
  should be reviewed in dependency order.
- BoxBrain pull request 3 still requires review and merge.

## Immediate next step

Select a disposable full Windows VM or dedicated lab computer, define
observation-only frame transport, and preserve the proven certificate gate
without enabling credentials or input.

## Long-term objective

Operate BoxBrain as the searchable coordination layer for an auditable
BrainConnect research controller that observes disposable lab systems through
narrow plugins before separately reviewed action capabilities are considered.
