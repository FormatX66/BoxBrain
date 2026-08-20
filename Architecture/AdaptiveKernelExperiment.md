# Aurum Adaptive Kernel Experiment

This branch is the standalone adaptive-kernel lane. It intentionally does not depend on StateWeave.

## Purpose

Test whether an adaptive hardware-realization layer can outperform fixed conventional hardware paths while preserving safety, reversibility, verification, and recoverability.

## Independence rule

This experiment must remain independently testable from StateWeave. Shared test fixtures may be used for comparison, but StateWeave is not a required runtime dependency.

## Core loop

```text
observed hardware state
  -> requested bounded hardware outcome
  -> candidate realizations
  -> rank by cost/confidence/risk
  -> execute reversible candidate
  -> verify actual hardware-visible outcome
  -> reward or penalize candidate confidence
  -> retain evidence
```

## Promotion rule

No standalone adaptive-kernel behavior replaces a working Aurum path until repeated side-by-side evidence shows equal or better verified outcomes, without reducing safety, reversibility, or recoverability.

## Initial metrics

- verified success rate
- rollback success rate
- candidate retries avoided after learning
- execution cost
- latency
- hardware-specific codelation eliminated
- regressions against conventional Aurum behavior
