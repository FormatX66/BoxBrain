# Codelation

Codelation is an experimental machine-native computation model for BoxBrain.
Instead of generating and executing human-readable source code, a seed observes
opaque states, records transitions, predicts the next state, and strengthens or
weakens relationships based on what actually happens.

## First seed

The first seed is a bootstrap experiment, not the final Codelation runtime. It
is implemented in Python only so it can run safely on a Raspberry Pi today.
The learned model is stored as a compact binary transition graph. It contains
no Python, shell commands, prompts, or executable instructions.

The seed converts observations into fixed-size state identities, records
transitions, predicts the strongest next state, validates predictions, and
persists relationships for later sessions. The human-readable layer is
diagnostic only; it summarizes the graph without becoming the graph.

## Safety boundary

Version 0 does not execute predicted states, modify the host, access the
network, or interpret observations as commands. It only learns and reports
state relationships. Any future actuation layer must be separately designed,
permission-gated, and reversible.

## Raspberry Pi quick start

```bash
cd Projects/Codelation
python3 seed/codelation_seed.py observe --model seed.bin boot
python3 seed/codelation_seed.py observe --model seed.bin ready
python3 seed/codelation_seed.py observe --model seed.bin boot
python3 seed/codelation_seed.py predict --model seed.bin boot
python3 seed/codelation_seed.py summary --model seed.bin
```

Run verification with `python3 -m unittest discover -s tests -v`.

## Development path

- Seed 0: passive transition learning and prediction.
- Seed 1: typed sensor adapters and confidence aging.
- Seed 2: outcome scoring and competing transition paths.
- Seed 3: sandboxed, permission-gated action proposals.
- Seed 4: replace the Python bootstrap with a minimal native runtime.
