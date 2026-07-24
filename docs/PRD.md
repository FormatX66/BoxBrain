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

## Current scaffold

- Flutter dashboard shell with Dashboard, Tasks, Policies, Plugins, and Logs.
- FastAPI health, task, policy, and manifest-discovery endpoints.
- In-memory queue that records tasks but executes nothing.
- Three policy profile definitions with shared containment invariants.
- Inert plugin example and a draft plugin contract.

## Out of scope for this scaffold

- Keyboard or mouse injection
- RDP, VNC, or HDMI capture
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

