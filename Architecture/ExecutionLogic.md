# State-First Execution Logic

This is the default execution policy for every BoxBrain/Aurum project, agent,
automation, build loop, deployment, diagnostic, and maintenance task.

## Core invariant

```text
intent -> observed current state -> required state -> delta -> constraints
       -> cheapest valid state-changing/evidence-producing action
       -> verification -> new state
```

Do not use this anti-pattern:

```text
prompt -> action -> error -> retry -> repeat
```

## Future Branch decision layer

When more than one materially different next state/action remains plausible,
apply the [Future Branch architecture](FutureBranch.md) inside the state-first
loop instead of prematurely choosing one path:

```text
observed state -> plausible futures -> evidence/risk/reversibility/authority
               -> keep safe branches warm
               -> promote one OR wait for more evidence
               -> execute through existing gates -> verify
               -> collapse / rollback / quarantine
```

Future Branch is mandatory when uncertainty materially affects the next action,
recovery path, diagnosis, user intent, transport, deployment, kernel/driver
candidate, or other consequential state transition. For trivial deterministic
work, do not manufacture branches just to satisfy the pattern.

Core rule: **anticipate aggressively; commit conservatively.** Preparation of a
safe/reversible future is not execution. Ambiguous ties wait. Failed candidates
are quarantined rather than replayed. Last Known Good remains an explicit
protected branch during speculative system mutations. Existing safety,
identity, permission, privacy, emergency-stop, and destructive-action gates
remain authoritative over any branch ranking.

## Mandatory pre-action gate

Before doing meaningful work, answer internally and proportionally:

1. **Intent:** What outcome is actually requested?
2. **Current state:** What is known from fresh evidence? Do not invent unseen state.
3. **Required state:** What must become true for the request to be satisfied?
4. **Delta:** What specifically differs between current and required state?
5. **Constraints/authority:** What safety, permission, resource, dependency, and reversibility constraints apply?
6. **Minimum useful action:** What is the least costly deterministic/reversible action that can either change the required state or produce genuinely new evidence?
7. **No-op/deduplication:** Has this action already been performed for the same state/evidence? If it cannot change state or add evidence, do not run it.
8. **Verification:** What machine-verifiable evidence proves the action had the intended effect?

For trivial requests this gate should take essentially no overhead. Complexity must
be proportional to the task.

## State classification

Never collapse all non-success outcomes into `failure`. Use explicit states:

- `success` — required state verified.
- `waiting` — a prerequisite or external event has not happened yet.
- `refused` — a safety/authority gate intentionally prevented the action.
- `blocked` — a concrete dependency is unavailable and no valid local path remains.
- `no_change` — action is unnecessary because state is already satisfied or unchanged.
- `failed` — an attempted valid action malfunctioned or verification disproved the expected result.

Expected `waiting`, `refused`, and `no_change` states must not create false-red
CI failures, retry storms, support incidents, or inbox noise.

## Retry rule

A retry is justified only when at least one of these changed:

- input/state,
- evidence,
- implementation,
- environment,
- dependency availability,
- hypothesis,
- authority.

If nothing changed, replaying the same action is not progress.

## Autonomous failure diagnosis and workaround rule

Failures must be inspected before they are escalated. Do not collapse actionable
transport/provider evidence into a generic exception name when exact evidence is
available.

For HTTP/API/provider failures, preserve the useful diagnostic surface when safe:

- exact status/error code,
- failure class,
- bounded response body or provider error payload,
- retry/rate/quota metadata such as `Retry-After` and remaining/reset limits,
- endpoint/provider/carrier involved,
- whether the failure affects the requested frontier or only one independent lane.

Classify at least these distinct cases when evidence supports them:

- rate/usage/quota limit,
- billing/resource limit,
- authorization/policy failure,
- transport/DNS/connectivity failure,
- controller/server/hosting failure,
- invalid request/client failure,
- unavailable external prerequisite.

Before asking the user, automatically attempt the cheapest bounded safe workaround
that can still satisfy the requested state, including when applicable:

1. continue independent lanes that do not depend on the failed resource,
2. use cached/verified state instead of repeating the same request,
3. use an already-authorized alternate carrier/route/provider,
4. fall back to deterministic local/open processing where capability is equivalent,
5. respect explicit `Retry-After`/reset evidence or use bounded backoff for transient failures,
6. preserve the checkpoint and resume from the same semantic state when the dependency changes.

Do not blind-retry a stable failure, burn metered usage to discover facts already
present in error telemetry, or ask the user to perform deterministic diagnosis the
system can perform itself.

Diagnostic response bodies, timestamps, retry counters, and changing rate-limit
headers are evidence, not semantic progress by themselves. They should not create
a retry/build loop unless the failure class, dependency availability, capability,
frontier, authority, or another state-changing fact changed.

## Resource/usage rule

Treat model/API usage, CI minutes, network transfers, hardware writes, and human
attention as finite resources.

Prefer in this order when capable of satisfying the state delta:

1. cached verified evidence,
2. deterministic local computation,
3. local/open model reasoning,
4. inexpensive external computation,
5. metered provider/model reasoning.

Do not spend a higher-cost resource when a lower-cost path can satisfy the same
state transition with equivalent evidence.

## Evidence/provenance rule

Every consequential result should preserve enough provenance to answer:

- what ran,
- where it ran,
- what implementation/version ran,
- what input/state it acted on,
- what resource/provider was consumed,
- what changed,
- how the result was verified.

Reasoning attributed to Aurum must identify the actual processor/runtime/model or
be marked `unattributed`/`unavailable`; submission of a prompt is not proof that
reasoning occurred.

## Automation/build rule

Telemetry, timestamps, heartbeat counters, iteration numbers, and regenerated
receipts are evidence, not progress by themselves. They may trigger another
build only when they change a capability, gate, verified state, unresolved
frontier, or other semantic state relevant to the requested outcome.

Deployment success is determined by deployment verification. Bookkeeping or
receipt publication failures must not retroactively turn an already-verified
deployment into a failed deployment.

## Escalation rule

Ask the user only when a genuinely unresolved human decision, credential,
permission, destructive authorization, subjective preference, or unavailable
external fact is required. Do not ask the user to solve a deterministic failure
that the system can inspect and fix itself.

Before escalation, the system must have already performed available bounded safe
diagnosis and exhausted authorized non-destructive alternatives that can satisfy
the same state delta. The escalation should report the evidence and the exact
human-only decision or input required, not merely report that an automation failed.

## Continuous review

Whenever a failure, repeated retry, false-red workflow, duplicate action,
unnecessary model call, or manual workaround is observed, check whether a
missed logic/process invariant caused it. Fix the invariant at the earliest
shared layer so future projects inherit the correction rather than patching only
the immediate symptom.
