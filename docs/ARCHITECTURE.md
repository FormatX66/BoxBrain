# Architecture

## Components

```text
Flutter UI
    |
    | authenticated local HTTPS
    v
Controller API -- Task/policy/audit state
    |                         |
    | out-of-process          | loopback-only SSH local-forward
    v                         v
Windows Sandbox observer    Kali Pi edge agent
    |                         |
    v                         v
Isolated Sandbox target     Explicitly authorized targets
```

The cloud model proposes structured intent. It never receives direct device
credentials and it does not call a transport plugin directly. The controller
validates each action against task state, target identity, declared plugin
capabilities, and the selected policy profile.

## Service boundaries

- **UI:** operator visibility, approvals, emergency stop, and configuration.
- **Controller:** authentication, task lifecycle, policy decisions, and audit.
- **Kali Pi edge agent:** authorized read-only diagnostics, bounded
  private-scope assessment, and advisory recommendations.
- **Planner adapter:** converts a task and observation into structured proposals.
- **Transport plugin:** obtains frames and performs narrowly typed input events.
- **Verifier:** decides whether an expected state change actually occurred.
- **Snapshot provider:** restores disposable targets between experiments.

## Observation process boundary

The Windows Sandbox status and PNG capture path runs through the enabled
`boxbrain.windows-sandbox-observer` plugin. The controller validates its strict
manifest, starts a new child process for each request, sends one correlated JSON
message, verifies the response identity and declared capability, then validates
frame type, size, and digest before returning bytes to the UI. The controller
passes a strict observation policy with every capture. The child independently
validates it, downsamples the frame, applies normalized black redaction regions,
and only then returns the PNG across the process boundary.

Frame retention is fixed to `none`: neither the controller nor the plugin writes
frame evidence to disk. A nonblocking single-capture gate rejects overlapping
requests, preventing refresh bursts from creating concurrent observer children.

The fixed-profile Sandbox launcher remains in the controller because it is an
audited, emergency-stop-gated capability rather than an observation. The plugin
protocol contains no input or launch operation. The child currently shares the
controller's Windows user identity; lower-privilege service isolation remains a
future boundary.

## Edge-agent boundary

The Kali Pi agent is reached only through a loopback SSH local-forward. The
controller validates the configured URL before startup and returns only a
sanitized inventory summary to the UI. The agent keeps its diagnostic records,
assessment evidence, SSH identity, and target-link state on the Pi.

The Pi has its own loopback status page for maintenance, but it is not a second
control plane. Its `agent` status object and `boxbrainctl agent` command describe
edge capabilities. The former `controller` command and module remain temporary
upgrade aliases for the existing deployment.

USB onboarding is a separate read-only HTTP service bound to the dedicated
`10.12.194.1` gadget address. Authorized USB-C targets are discovered
automatically. Authorized Wi-Fi/Ethernet targets are explicitly enrolled over
the Pi's local Unix control socket after private-route and key-only SSH
verification. Neither path is exposed through the controller's edge-agent
status client.

## Operator remote-session boundary

Remote target profiles are durable controller records for private, loopback, or
link-local hosts. The manager supports the Pi USB-C SSH path, general SSH,
WinRM, RDP, and explicitly acknowledged lab-only Telnet. A probe opens only a
bounded TCP connection to the registered host and port. A session request
selects a fixed argument vector for the matching operating-system client; the
API accepts no executable, script, or command input.

Session launch requires the dashboard's exact `OPEN` confirmation and a clear
persistent emergency stop. Telnet additionally requires the exact plaintext-risk
phrase. Passwords are never accepted or stored: SSH uses the agent or dedicated
Pi identity, WinRM uses the current Windows identity, and RDP handles credentials
interactively. These are human-controlled terminals or desktops, not an action
executor, and queued tasks cannot drive them.

## AI diagnostic executor boundary

The diagnostic planner is an OpenAI Agents SDK call with a typed output schema
and no tools. It may select only `system_health`, `disk_usage`, `memory_usage`,
or `uptime` for the built-in Kali Pi. The operator sees the exact typed plan,
expected evidence, risk note, model, and token use before anything can run.

Execution is a separate controller operation requiring the exact value `RUN`.
Inside the shared action lock it rechecks the persistent emergency stop, built-in
target identity, and private address resolution. The user's goal and model text
never enter the process arguments; the selected enum maps to a fixed SSH command.
SSH is noninteractive and host-key strict, commands have a hard deadline, and
returned output is byte-capped. Audit records contain proposal and result
metadata but not raw diagnostic output. Proposals expire and cannot be replayed.

This is not the queued-task executor and does not give the model a terminal.
General SSH, WinRM, RDP, and Telnet targets remain human-operated sessions.

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

