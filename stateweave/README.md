# StateWeave experimental lane

This directory contains the first executable prototype of Aurum StateWeave.

StateWeave is a machine-state representation, not a new human programming language. The Python runtime here exists only to bootstrap and test the representation on today's hardware.

## Current v0 capabilities

- numeric machine-state nodes,
- declarative predicates and goals,
- invariants that cannot be crossed,
- costed state transitions,
- lowest-cost path planning,
- deterministic `SWV1` binary serialization,
- transition receipts using before/after state hashes.

## Run tests

```sh
cd stateweave
python -m unittest -v test_stateweave.py
```

The StateWeave GitHub Actions workflow is isolated from the normal Aurum build so experiments can fail without blocking the working system.

## Parallel comparison plan

The next useful step is not to rewrite Aurum. Pick bounded existing capabilities and represent the same required state in StateWeave. Run both lanes and compare:

1. final verified state,
2. invariant preservation,
3. number and cost of operations,
4. serialized representation size,
5. amount of conventional codelation required,
6. recoverability and evidence quality.

Initial candidates are a BoxBrain deployment-state transition and one Raspberry Pi transport/recovery path.

See `Architecture/StateWeave.md` for the architecture and promotion rules.
