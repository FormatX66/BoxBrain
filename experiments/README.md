# Aurum Experiment Race

Aurum currently maintains four independently measurable lanes:

1. `main` — conventional Aurum implementation.
2. `stateweave-experimental` — StateWeave without the adaptive kernel.
3. `adaptive-kernel-experimental` — adaptive kernel without StateWeave.
4. `stateweave-adaptive-kernel` — combined StateWeave + adaptive-kernel hypothesis.

The combined lane is not assumed to be superior. StateWeave and the adaptive kernel must remain independently testable so the combination can be accepted or rejected by evidence.

## Automatic execution

`.github/workflows/aurum-experiment-race.yml` is the central read-only race controller. It runs when:

- `main` changes,
- one of the three experiment-specific workflows completes,
- an `aurum-experiment-frontier` repository dispatch is received,
- the daily fallback audit fires,
- or a manual workflow dispatch is requested.

Each experimental branch also has its own branch-specific CI workflow.

## Common benchmark

Every lane implements `experiments/benchmark.py` and currently runs the shared `bounded_recovery_v1` semantic case:

- initial state: target off, simulated temperature safe,
- desired state: target on,
- invariant: simulated temperature must remain within the declared safe bound,
- candidate 1: produces the wrong state,
- candidate 2: reaches the requested target but violates the invariant,
- candidate 3: reaches the requested target while preserving the invariant.

The benchmark records first-run attempts, second-run attempts, rollback behavior, learned avoidance, machine-native representation, semantic planning, adaptive-hardware capability, and final verified state.

This synthetic benchmark is only the first common contract. It does not declare a production winner.

## Promotion rule

No experimental lane is automatically merged or promoted. Promotion requires repeated shared evidence on a real Aurum capability showing equal or better:

- verified outcome,
- safety/invariant preservation,
- recoverability,
- resource cost,
- and useful reduction in codelation or fixed hardware-specific logic.

## Next common frontiers

1. A real BoxBrain deployment-state transition.
2. A read-only/reversible Pi transport or recovery operation.
3. A hardware-observation case where the adaptive lane can learn from repeated evidence without writing firmware or unsafe device state.

The scorecard is produced as a GitHub Actions artifact and job summary. A red lane remains evidence and must not prevent the other racers from completing.
