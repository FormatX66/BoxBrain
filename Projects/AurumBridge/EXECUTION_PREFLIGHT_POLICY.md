# Aurum Execution Preflight Policy

Status: authoritative execution doctrine for Aurum bridge/bootstrap/repair workflows.

## Principle

Do not issue a consequential first command from a single assumed happy path.

Before execution, Aurum must build a bounded decision tree from observable state, enumerate credible outcomes, select the appropriate branch, and make the operation idempotent where practical.

Required sequence:

1. Preflight
2. Enumerate observable states and credible failure branches
3. Select branch from evidence
4. Execute the smallest safe action
5. Verify the intended postcondition
6. Self-recover or retry safely when a known branch fails
7. Escalate to the human only when no safe autonomous branch remains or explicit authority is required

## Mandatory preflight classes

For local/remote machine work, inspect as applicable:

- target identity: hostname, OS, architecture, expected role, runner/agent identity
- authority: administrator/SYSTEM state, authorization scope, destructive-operation approval
- connectivity: GitHub/API/network reachability and required endpoints
- local installation state: services, processes, configured roots, files, partial installs, stale remnants
- remote/control-plane state: registrations, duplicate names, stale records, labels, queued jobs, permissions
- toolchain availability: PowerShell, Git, GitHub CLI, winget/package manager, Docker/build tools, required versions
- authentication: current login/token state and whether interactive auth may be required
- storage/device identity: bus type, model, serial, size, boot/system flags, online/offline state
- input/artifact readiness: exact commit/head, successful workflow, artifact existence, checksum, expiry
- concurrency/ownership: competing jobs, locks, other candidate devices/runners, race conditions
- rerun behavior: whether the command is safe after partial completion or previous success
- rollback/recovery: how to restore service/device state if the operation fails midway
- verification: exact success markers, hashes, service state, evidence file, or other postcondition

## Credible outcome enumeration

Before generating the first command, explicitly account for states such as:

- healthy/already complete
- installed and running
- installed but stopped/disabled
- service missing while files/configuration remain
- files/configuration missing while remote registration remains
- stale or duplicate remote registration/name collision
- partial/corrupt prior installation
- authentication missing/expired
- required tool missing
- endpoint/network unavailable
- insufficient privilege
- no target device
- exactly one safe target device
- multiple candidate devices
- target is boot/system/protected and must be refused
- artifact missing/expired/mismatched
- command already executed and should not repeat destructively
- transient failure suitable for bounded retry
- unknown state requiring evidence collection before mutation

This is a bounded-completeness requirement, not a claim that every physically possible event can be predicted. Aurum must cover all credible branches discoverable from available evidence before asking the human to run the first command.

## Command design requirements

Commands/scripts should, where practical:

- perform their own preflight rather than require the human to run diagnostic commands one at a time
- emit machine-readable state plus concise human-readable markers
- avoid terminating before reporting useful evidence
- distinguish WAITING/REFUSED states from actual defects
- be idempotent or detect already-complete state
- preserve and restore reversible machine/device state in finally/cleanup paths
- pin external inputs when cache/staleness could change behavior
- use unique, explicit identities/labels for consequential workers
- refuse ambiguous destructive targets
- record durable receipts for consequential success

## Human escalation rule

Do not make the human discover known branches by trial and error. Human input should be requested only for:

- explicit authorization that cannot be inferred or already exists
- interactive authentication that cannot be safely automated
- physical actions the software cannot perform
- genuinely ambiguous identity/ownership
- novel failure with no safe evidence-backed recovery branch

## Current runner/USB incident lesson

The Aurum Windows runner recovery should have preflighted local service state, configured runner roots, GitHub-side stale registration, runner naming/labels, GitHub CLI/auth state, network reachability, machine identity, USB model/serial/safety, image readiness, and rerun behavior before issuing the first repair command.

Future Aurum bridge, bootstrap, repair, install, flash, and machine-control workflows should treat this policy as a default invariant.