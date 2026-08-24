# Future Branch Execution Routes

Future Branch answers **what should happen next**. Execution Routes answer **how the current context can actually make it happen**.

The route field is generated before asking the user to carry work manually.

## Route families

A candidate route may be:

- `direct-local`: the current execution context can perform the bounded capability itself;
- `connected-capability`: a connected app/tool exposes the required bounded operation;
- `authorized-runner`: an already-authorized machine/runner can execute the bounded operation;
- `workspace-handoff`: another execution surface is materially better positioned to complete the task;
- `human-assisted`: a person must physically act, transfer context, approve a boundary, or perform a step no machine route can currently perform safely.

Human interaction is a valid route, not a failure. It should not become the default simply because the current route is inconvenient.

## Ranking inputs

Rank each route independently using fresh evidence for:

- availability;
- authority readiness;
- expected success;
- evidence quality;
- autonomy;
- reversibility;
- risk;
- setup cost;
- latency cost;
- number of required human steps;
- freshness/staleness.

Machine-capable routes receive a modest preference when their utility is otherwise similar. This preference is not absolute: a human-assisted route may win when it is materially safer, faster, more reliable, or the only available path.

## Invariants

1. **Route choice grants no authority.** Destructive, credential, physical, privacy, and policy gates remain sovereign.
2. **Stale routes do not compete.** If target identity, verified artifact, state, authority, or environment changed, re-resolve the route field before execution.
3. **Human effort is a cost, not a prohibition.** Ask for human interaction only when its expected value beats the available machine routes or a real boundary requires it.
4. **Keep alternates warm.** A failed connector, runner, transport, or handoff should fall through to a prepared alternate instead of restarting linear reasoning.
5. **Verify the result.** Route completion is not task success; the resulting state still requires the proof contract of the parent Future Branch.

## Example: Tiny Seed physical flash

For an authorized Tiny Seed flash, the route field could contain:

1. direct bounded local flash capability on the machine holding the USB;
2. connected authorized runner on that machine;
3. workspace handoff to a local execution surface;
4. human copy/paste or command execution as a fallback.

Before requesting the human fallback, Aurum should already know whether the earlier routes exist, what evidence they require, and what would make each route fail. If the person happens to be sitting at the machine and human interaction is genuinely the lowest-risk/lowest-latency route, it may still be selected deliberately rather than accidentally.

## Relationship to Future Branch

Future Branch maintains the likely intent/state/diagnostic futures. Each promoted or prepared action may have its own bounded execution-route field. This creates two coupled decisions:

```text
what future is useful?
    -> Future Branch
how can that future be realized from here?
    -> Execution Route field
    -> authority/policy boundary
    -> execution
    -> verification
```

The long-term goal is that likely actions have both their answer/evidence **and their execution paths** warmed before the user asks for them.
