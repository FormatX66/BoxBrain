# Knowledge and Execution Data Flow

```mermaid
sequenceDiagram
    participant Human
    participant BoxBrain
    participant Project
    participant Verification
    participant Handoff

    Human->>BoxBrain: Objective and authority
    BoxBrain->>BoxBrain: Read indexes, newest handoff, decisions, and changes
    BoxBrain->>Project: Execute highest-priority in-scope work
    Project->>Verification: Tests, link checks, and status checks
    Verification-->>BoxBrain: Evidence and remaining risks
    BoxBrain->>Handoff: Decisions, changes, blockers, and next step
    Handoff-->>Human: Human summary
```

## Repository update order

1. Read [Repository Index](../Admin/RepositoryIndex.md).
2. Read the newest entry in [Session Index](../Admin/SessionIndex.md).
3. Read [Decision Index](../Admin/Decisions.md) and
   [Change Index](../Admin/ChangeLog.md).
4. Update [Master TODO](../Admin/MasterTODO.md).
5. Work in the registered implementation repository.
6. Verify that repository.
7. Update the project index and BoxBrain cross-project records.
8. Create the next session bundle.

Detailed code-level data flow remains in each project’s canonical
documentation.

## Current BrainConnect control flow

1. The operator selects the enabled disposable VM and creates an `open` task.
2. The dashboard submits a bounded typed operation.
3. The controller transactionally rechecks emergency stop, task state, target
   state, policy, and the 500-operation limit.
4. The operation is stored as `queued`; the audit event records type, size,
   digest, target, and task without copying sensitive content.
5. A manual execution request re-probes the pinned RDP certificate and
   atomically claims the operation as running.
6. The fixed subprocess receives bounded JSON through standard input and
   returns one identity-matched result.
7. The controller persists terminal status and output size/digest, while raw
   output is returned transiently to the authenticated dashboard.
8. The packaged fixture proves this complete path without touching the VM.
   The native pointer connector implements the same protocol, reads
   target-bound systemd credentials only after exact endpoint and certificate
   verification, and is not yet installed or enabled on the Pi.
