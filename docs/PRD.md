# BoxBrain Alpha Product Requirements

## Mission

Give a human operator one auditable place to connect an AI planning service to
an isolated, resettable computer lab.

## Alpha outcome

The alpha is complete when an operator can:

1. Open the Flutter dashboard.
2. See controller health and the active policy profile.
3. Register one isolated target through a transport plugin.
4. Queue one structured task.
5. Observe proposed and completed actions in an immutable event stream.
6. Stop the run and restore the target from a known snapshot.

## Current implementation

- Flutter dashboard with Dashboard, Target, Tasks, Policies, Plugins, and Logs.
- FastAPI health, task, event, policy, target, and plugin endpoints.
- SQLite task persistence with database-enforced append-only audit events.
- Read-only Windows Sandbox discovery and local frame capture.
- Target allowlisting and three policy profiles with containment invariants.
- Persistent, audited emergency stop with guarded reset and effectful-request gate.
- No task or input execution.

## Out of scope for this scaffold

- Keyboard or mouse injection
- Remote RDP, VNC, or HDMI transport control
- Shell command execution
- Cloud model calls or secret storage
- Automatic code modification
- Background service installation
- Bootable USB or Raspberry Pi image creation

## Alpha success measures

- Every action has a request, decision, result, timestamp, and correlation ID.
- An emergency stop prevents new actions within one controller cycle.
- A task never crosses its configured target boundary.
- A failed verification produces a visible failure rather than an assumed pass.
- A clean snapshot can be restored after every experiment.

