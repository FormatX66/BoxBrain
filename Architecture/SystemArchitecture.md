# System Architecture

BoxBrain separates ecosystem knowledge from implementation source while making
both discoverable from one index.

```mermaid
flowchart TD
    BB["BoxBrain knowledge and coordination repository"]
    PI["Project and repository indexes"]
    GOV["Decisions, roadmap, changes, and handoffs"]
    BC["BrainConnect implementation repository"]
    PICTRL["Kali Pi controller and edge agent"]
    WINLAB["Checkpointed Hyper-V Windows lab"]
    AF["AgentFramework (proposed)"]
    SEC["Security (proposed)"]
    RES["Research (proposed)"]
    WEB["Website projects (discovery)"]

    BB --> PI
    BB --> GOV
    PI --> BC
    BC --> PICTRL
    PICTRL --> WINLAB
    PI --> AF
    PI --> SEC
    PI --> RES
    PI --> WEB
    BC -. future shared contracts .-> AF
    BC -. cross-project controls .-> SEC
    BC -. benchmarks and evidence .-> RES
```

## Boundaries

- BoxBrain owns cross-project discovery, dependencies, priorities, decisions,
  and handoffs.
- Each registered repository owns its code, tests, and detailed technical
  documentation.
- A planned project receives only a project index until source or requirements
  are discovered.
- Links replace copied documents.

## Current dependency path

The active execution path is BoxBrain governance to the BrainConnect
repository, then to the USB-bound Kali Pi controller and edge agent, and then
to the checkpointed Windows lab on the Pi-only network. BrainConnect has
verified and audited the full target's certificate-only RDP identity boundary;
it now accepts bounded, audited open-profile operations into a durable queue.
It also has a disabled-by-default out-of-process protocol, exact certificate
recheck, durable execution states, bounded result metadata, and deterministic
no-action fixture. The native transport connector now supports
certificate-pinned pointer movement, Unicode text, fixed allowlisted key
events, and bounded multi-step keyboard sequences in one connection. Its
amd64 and arm64 artifacts are verified, and the sequence-capable arm64
artifact is installed on the Pi. Windows event evidence proved exact-user
authentication and reconnection to the intended console session. Slow-path
keyboard delivery then independently launched Task Manager and Notepad. The Pi
is inert again with execution disabled, no drop-in, no encrypted target
credentials, and no temporary runner; the VM is restored to its exact clean
checkpoint. Observation-only frame, cursor, and visible-content verification
are the active pending track.

See [BrainConnect’s canonical architecture](../../BrainConnect/docs/ARCHITECTURE.md)
for component-level details and [Integrations](Integrations.md) for registered
boundaries.
