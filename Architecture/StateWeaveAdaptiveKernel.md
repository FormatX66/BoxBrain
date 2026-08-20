# StateWeave + Adaptive Kernel Experiment

This lane tests whether Aurum StateWeave and the adaptive kernel are stronger as a single feedback system than as separate ideas.

It is experimental and non-blocking. It must not replace or modify a working Aurum kernel/runtime path until repeated side-by-side tests prove a verified improvement.

## Hypothesis

StateWeave should own **what state must become true**. The adaptive kernel should own **how this exact machine can most safely and efficiently make that state true**.

```text
observed hardware state
        |
        v
     StateWeave
(current state, goal, invariants, allowed transitions)
        |
        v
 verified logical transition plan
        |
        v
 Adaptive Kernel Fabric
(candidate hardware realizations + confidence + cost + reversibility)
        |
        v
 CPU / device / transport action
        |
        v
 machine observation + verification
        |
        +------> StateWeave new state
        |
        +------> adaptive-kernel confidence/model update
```

The two layers deliberately have different responsibilities:

- **StateWeave:** machine-native state, relationships, goals, constraints, planning, semantic verification.
- **Adaptive kernel:** hardware discovery, capability mapping, candidate lowering, device-specific execution, rollback/fallback, observed behavior, confidence learning.
- **Codelation layer:** temporary bootstrap/compatibility code used to reach existing Linux, firmware, drivers, compilers, and devices. It is not the intended canonical representation.

## Why they complement each other

An adaptive kernel without a machine-native state model can become a collection of learned procedures. StateWeave gives those procedures a stable semantic target and explicit invariants.

StateWeave without an adaptive hardware layer can plan a correct state transition but still depend on fixed hand-written mappings to make it happen. The adaptive kernel gives StateWeave a machine-specific realization layer that can improve as evidence accumulates.

Together the loop becomes:

```text
goal -> state delta -> safe transition -> hardware realization
     -> observation -> verification -> confidence update -> new state
```

## v0 experiment

The first experiment is intentionally a simulated hardware fabric. No live kernel, firmware, register, storage, or device mutation is performed.

For every StateWeave transition, the adaptive layer may know multiple candidate realizations. Each candidate has:

- numeric action identity,
- compatible StateWeave transition identity,
- execution cost,
- confidence score,
- reversibility flag,
- bounded simulated hardware action.

The kernel fabric ranks valid candidates, attempts the best one, verifies the resulting hardware state against the StateWeave transition effects, and only then accepts the transition. A reversible failed or misverified candidate is rolled back and a bounded fallback may be tried. Success raises confidence; failure lowers it.

## Promotion rules

This combined lane cannot replace a working Aurum path merely because it is smaller or novel. Promotion requires repeated evidence that it is at least equivalent on:

1. final verified state,
2. invariant preservation,
3. recoverability,
4. deterministic behavior where determinism is required,
5. resource cost,
6. failure classification and bounded fallback.

Prefer it only when it additionally improves one or more of:

- less human-authored codelation,
- smaller representation,
- fewer fixed hardware assumptions,
- faster adaptation to exact hardware,
- better recovery from changed hardware behavior,
- lower execution/resource cost.

## Safety boundary

The v0 adaptive fabric is a simulator. A later hardware-backed version must begin read-only, then move through reversible/isolated operations before any live kernel or device mutation. Every consequential operation needs before/after evidence and an explicit authority boundary.

## Initial comparison targets

1. Choose between an exact-hardware lowering and a generic compatibility lowering for the same StateWeave transition.
2. Detect a candidate that reports success but produces the wrong hardware state; roll it back and use a verified fallback.
3. Preserve StateWeave invariants while hardware candidates change.
4. Retain learned confidence across repeated equivalent transitions.
5. Compare conventional fixed mapping vs StateWeave-only vs StateWeave+adaptive-kernel on state correctness, cost, representation size, and codelation.

## Long-term target

```text
intent
 -> StateWeave semantic state model
 -> verified state transition
 -> adaptive hardware lowering
 -> native CPU/GPU/device operation
 -> hardware observation
 -> StateWeave receipt + adaptive model update
```

At that point traditional source languages remain useful views and compatibility outputs, but they are no longer the system's canonical description of what the machine is or what it should do.
