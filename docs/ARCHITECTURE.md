# Architecture

## Components

```text
Flutter UI
    |
    | authenticated HTTPS / WebSocket
    v
Controller API ── Task state machine ── Policy decision point
    |                                      |
    | versioned local protocol             | allow / confirm / deny
    v                                      v
Out-of-process plugins  ───────────────> Audit event store
    |
    v
Isolated, allowlisted lab target
```

The cloud model proposes structured intent. It never receives direct device
credentials and it does not call a transport plugin directly. The controller
validates each action against task state, target identity, declared plugin
capabilities, and the selected policy profile.

## Service boundaries

- **UI:** operator visibility, approvals, emergency stop, and configuration.
- **Controller:** authentication, task lifecycle, policy decisions, and audit.
- **Planner adapter:** converts a task and observation into structured proposals.
- **Transport plugin:** obtains frames and performs narrowly typed input events.
- **Verifier:** decides whether an expected state change actually occurred.
- **Snapshot provider:** restores disposable targets between experiments.

## Observation process boundary

The Windows Sandbox status and PNG capture path runs through the enabled
`boxbrain.windows-sandbox-observer` plugin. The controller validates its strict
manifest, starts a new child process for each request, sends one correlated JSON
message, verifies the response identity and declared capability, then validates
frame type, size, and digest before returning bytes to the UI.

The fixed-profile Sandbox launcher remains in the controller because it is an
audited, emergency-stop-gated capability rather than an observation. The plugin
protocol contains no input or launch operation. The child currently shares the
controller's Windows user identity; lower-privilege service isolation remains a
future boundary.

## Data flow

1. The UI submits a task tied to an allowlisted target and policy profile.
2. The controller records the task and obtains a target observation.
3. A planner proposes one typed action with expected evidence.
4. The policy layer returns `allow`, `confirm`, or `deny`.
5. An allowed action is sent to one capability-scoped plugin.
6. The verifier compares before/after evidence.
7. The controller records the decision and result before continuing.

## Persistence

The controller stores task state and audit events in SQLite. Task creation and
its `task.queued` event are committed in one transaction. SQLite triggers reject
updates or deletions from the event table, while the API exposes events as
read-only records. PostgreSQL can replace SQLite when multi-controller
deployment is required.

