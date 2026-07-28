# BoxBrain Master Architecture

## Current architecture version

**1.0**

Version 1.0 defines the canonical BoxBrain ecosystem direction while preserving
the existing controller, processing crew, remote-target manager, Kali Pi edge
agent, diagnostic executor, and Windows Sandbox observer.

```text
Bruce (User)
    |
Arkmatx Interface
    |
BoxBrain (AI Orchestrator)
    |
Specialized Agents
    |
Brain Connect
    |
Authorized Machine / VM / Raspberry Pi / Cloud Service
```

The live manifest is available from `GET /api/v1/architecture`. It is also shown
in the dashboard's **Fleet** workspace.

## Changes made

- Added a versioned, machine-readable architecture manifest.
- Added the twelve-agent system roster without renaming the existing ten-agent
  processing crew.
- Added a durable Fleet Manager inventory.
- Added one durable BoxBrain Machine ID per fleet record.
- Linked fleet records to authorized remote targets by identifier without
  copying host credentials.
- Added a machine capability catalog.
- Added a resumable, ordered 16-step provisioning workflow.
- Added local audit events for registration, import, provisioning start, and
  provisioning-step completion.
- Added a Fleet dashboard for inventory, target import, machine registration,
  provisioning progress, and architecture visibility.

## Updated agent list

| Agent | Maturity | Current implementation boundary |
| --- | --- | --- |
| Orchestrator | Operational | Existing processing orchestrator |
| Knowledge Manager | Operational | Archivist and project memory |
| Memory Manager | Operational | Processing store and memory search |
| Task Manager | Operational | Dispatcher and durable task stores |
| Repository Manager | Planned | Operator-guided repository pipeline |
| Website Manager | Planned | Operator-guided site pipeline |
| Deployment Manager | Planned | Operator-guided build/release pipeline |
| Diagnostics Manager | Operational | Diagnostic executor and Pi edge agent |
| Fleet Manager | Foundation | Durable fleet inventory and status |
| Machine Provisioning Agent | Foundation | Resumable guided checklist |
| Brain Connect | Foundation | Remote-target and edge-agent transports |
| Capability Registry | Foundation | Fleet capability inventory |

The processing crew remains the provider-neutral intake/planning layer. The
system roster describes long-lived ecosystem responsibilities. A system agent
may map to one or more existing components; the two lists are intentionally not
forced into one incompatible identifier set.

## Provisioning workflow

The workflow follows the canonical sixteen steps:

1. Detect machine.
2. Confirm machine name.
3. Generate Machine ID.
4. Open Google account setup.
5. Complete CAPTCHA.
6. Confirm dedicated Gmail.
7. Confirm dedicated Google Drive.
8. Create the standard Drive folders.
9. Configure GitHub identity.
10. Clone required repositories.
11. Install required software.
12. Register Brain Connect.
13. Register Fleet Manager.
14. Register capabilities.
15. Run diagnostics.
16. Complete the provisioning report.

Identity, fleet, and capability registration steps are completed locally when
the required data already exists. External-account steps are operator-guided.
BoxBrain never attempts CAPTCHA completion and never asks the operator to store
passwords, recovery codes, SSH private keys, or API keys in a fleet record.

Only the current pending step can be marked complete. Progress is stored in
SQLite and resumes after a controller restart. Completing the final step changes
the machine status to `ready`.

## API

- `GET /api/v1/architecture`
- `GET /api/v1/system-agents`
- `GET /api/v1/fleet`
- `GET /api/v1/fleet/machines`
- `POST /api/v1/fleet/machines`
- `POST /api/v1/fleet/import-targets`
- `GET /api/v1/fleet/machines/{machine_id}/provisioning`
- `POST /api/v1/fleet/machines/{machine_id}/provisioning`
- `POST /api/v1/provisioning/{run_id}/steps/{step_id}/complete`

Mutation requests use exact confirmation values. Normal API-token, trusted-host,
CORS, TLS, no-store, and append-only audit protections still apply.

## Compatibility and migration

No destructive data migration is required. New `fleet_machines`,
`provisioning_runs`, and `provisioning_steps` tables are created with
`CREATE TABLE IF NOT EXISTS` in the existing SQLite database.

Existing remote targets can be imported explicitly from the Fleet dashboard.
The import is idempotent by remote-target identifier. It records metadata and
capabilities already exposed by the target registry; it does not copy
credentials or create a new remote execution path.

Existing safety boundaries remain:

- Autonomous queued-task execution stays disabled.
- AI diagnostics remain limited to fixed read-only Kali Pi actions.
- Diagnostic execution still requires the exact `RUN` confirmation.
- Operator remote sessions still require `OPEN`.
- Telnet remains separately guarded and marked insecure.
- Emergency stop continues to gate effectful controller actions.

## Known risks

- Provisioning completion is currently operator-attested; device-side evidence
  is not yet attached to each checklist step.
- Machine health and resource history are not yet collected into Fleet Manager.
- External account lifecycle and recovery remain the operator's responsibility.
- Brain Connect is still represented by the existing remote-target and edge
  transports rather than a standalone signed protocol.
- Repository, website, and deployment managers are architectural roster entries
  but do not yet have controller executors.

## Suggested next steps

1. Add signed machine heartbeats and last-seen status to Fleet Manager.
2. Add capability discovery reports from the Pi and future desktop edge agent.
3. Attach approval-gated diagnostic evidence to provisioning step 15.
4. Generate a downloadable provisioning report after step 16.
5. Design the reviewable Repository Manager change/commit/push pipeline.

## Potential improvements

- Version every architecture manifest and expose a read-only history endpoint.
- Add machine search, labels, ownership, and lifecycle states.
- Add capability schema versions and evidence timestamps.
- Add encrypted references to external secret managers without storing secrets
  in BoxBrain.
- Add provisioning templates for Windows, Kali, Raspberry Pi OS, and cloud
  services.

## Future expansion ideas

- Multiple BoxBrain controller nodes backed by PostgreSQL.
- Signed Brain Connect identities and mutual TLS.
- Offline-first machine queues with replay protection.
- GPU, accelerator, sensor, and robotics capability types.
- Cloud resource and website inventory as fleet-adjacent managed resources.
