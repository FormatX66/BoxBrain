# Aurum StateWeave

StateWeave is Aurum's experimental machine-native state representation. It is not intended to become another human programming language. Its purpose is to represent observed state, desired state, constraints, valid transitions, cost, and verification in a compact form that can eventually be lowered directly into hardware-specific execution.

## Core idea

Traditional source code describes a human-authored sequence of operations. StateWeave instead describes:

- current machine state,
- desired state,
- invariants that must remain true,
- valid state transitions,
- transition cost,
- verification evidence.

The runtime selects the lowest-cost valid path from current state to required state while preserving invariants.

## v0 execution model

StateWeave v0 uses numeric identifiers in the execution core. Human names are optional views and must not be required to execute the weave.

```text
observed state + goals + invariants + transitions
                 |
                 v
          StateWeave planner
                 |
                 v
        lowest-cost valid path
                 |
                 v
       transition execution
                 |
                 v
       machine-verifiable receipt
                 |
                 v
             new state
```

This directly complements Aurum's existing state-first execution policy.

## Binary format

The first prototype uses a deterministic binary envelope identified by `SWV1`.

Core values are currently:

- node identifiers: unsigned 32-bit integers,
- values: signed 64-bit integers,
- comparison operators: compact numeric opcodes,
- transitions: numeric ID, cost, flags, predicates, and effects,
- effects: set or add,
- state serialization: canonical node ordering.

The Python implementation is scaffolding used to test the representation. Python is not the intended long-term StateWeave execution language.

## Verification

Every executed transition produces a receipt containing:

- transition ID,
- hash of the state before the transition,
- hash of the resulting state.

A plan is only successful if the final state satisfies the declared goals and every intermediate state preserves the invariants.

## Parallel-development rule

StateWeave remains experimental until it demonstrates equivalence or improvement over existing Aurum paths. Existing working Aurum behavior must not depend on StateWeave during this phase.

For candidate capabilities, test both paths:

```text
existing implementation -> observed result
StateWeave model         -> observed result
                         -> compare state/evidence/cost
```

Promote a capability only after StateWeave repeatedly produces the same verified outcome, or a demonstrably better outcome, without reducing safety or recoverability.

## v0 success criteria

1. Deterministic binary round-trip.
2. Constraint-safe planning.
3. Lowest-cost valid transition selection.
4. Verifiable execution receipts.
5. No dependency on human-readable node names.
6. CI tests independent from the main Aurum build.

## Next experiments

- model a real BoxBrain/Aurum deployment state transition,
- model one Pi transport/recovery operation,
- compare StateWeave planning with the current controller path,
- add typed values beyond signed integers,
- add resource/capability relationships,
- add concurrent independent transitions,
- define a hardware-lowering interface,
- benchmark representation size, planning cost, and codelation eliminated.

## Long-term direction

The target architecture is:

```text
intent
  -> StateWeave
  -> verified state plan
  -> hardware-specific lowering
  -> CPU/GPU/device instructions
  -> observed new state
  -> StateWeave update
```

Traditional source code then becomes a generated compatibility view or bootstrap implementation rather than Aurum's canonical source of truth.
