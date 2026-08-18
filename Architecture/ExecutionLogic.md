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

## Continuous review

Whenever a failure, repeated retry, false-red workflow, duplicate action,
unnecessary model call, or manual workaround is observed, check whether a
missed logic/process invariant caused it. Fix the invariant at the earliest
shared layer so future projects inherit the correction rather than patching only
the immediate symptom.
