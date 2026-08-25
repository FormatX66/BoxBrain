# Adaptive Kernel

Adaptive Kernel is Aurum's independently testable lane for turning observed
machine facts into the smallest verified capability set needed by the current
machine.

## Current state

Generation 0 remains the planning boundary in `adaptive_kernel.py`: it evaluates
capability rules and emits auditable Future Branch proposals without binding a
driver or changing a machine.

Generation 1 adds `runtime.py`, a bounded simulated feedback loop:

```text
observed facts -> low-risk plan -> ranked realization candidates
              -> isolated proposed state -> independent observation
              -> invariant + claim/observation verification
              -> promote OR discard/rollback -> confidence update
              -> quarantine repeated failures -> auditable receipt
```

The runtime provides concrete mechanisms that the plan-only prototype lacked:

- deterministic ranking by learned confidence, cost, and stable identity;
- before/proposed/observed/after hashes for every attempted state transition;
- fail-closed risk, reversibility, compatibility, and invariant gates;
- bounded fallback after a failed candidate;
- explicit `success`, `no_change`, `refused`, `blocked`, and `failed` states;
- durable JSON-serializable learning checkpoints;
- quarantine after repeated equivalent failures, with explicit release only
  after evidence or implementation changes.

## Safety boundary

This is still a simulator. A realization callback receives a copy of primitive
state and returns a complete proposed state. Other callbacks receive read-only
views. The default observer mirrors the proposed simulated state; callers can
supply a separate pure observer to exercise claim-versus-observation checks. The
runtime has no live kernel, driver, firmware, filesystem, device-I/O, or
privileged carrier. It refuses non-low-risk rules and non-reversible candidates
even if a caller tries to force them into a plan.

Actual hardware execution belongs in a later isolated carrier with independent
authority, recovery, canary, and Last Known Good gates. A successful simulated
realization is evidence for that frontier; it is not permission to cross it.

## Run the focused suite

```powershell
python -m unittest discover -s Projects/AdaptiveKernel/tests -p "test_*.py"
python -m unittest Projects.StateWeaveKernel.tests.test_bridge
```
