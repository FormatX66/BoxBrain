# Aurum Seed Recovery Architecture

Status: **Mandatory base-seed requirement**

## Core invariant

> No new state may destroy the last proven working state.

Aurum may experiment and adapt aggressively, but promotion of a new seed/state must be conservative and reversible.

## Required base-seed protections

### 1. A/B seed slots
- Never overwrite the currently proven bootable seed in place.
- Build or install a candidate into the inactive slot.
- Promote the candidate only after required boot and health validation succeeds.
- Preserve the prior proven slot until the new candidate becomes trusted.

### 2. Last Known Good (LKG)
- Maintain an explicit LKG pointer/state independent of the active candidate.
- A candidate cannot become LKG until it passes the defined health gate.
- LKG must remain recoverable if the active seed is corrupt, incomplete, or non-booting.

### 3. Independent State Guardian / watchdog
- Recovery logic must be smaller, more conservative, and less mutable than the adaptive seed.
- Normal Aurum adaptation must not be allowed to casually rewrite or disable its recovery mechanism.
- The Guardian has final local authority to reject an unhealthy candidate and restore LKG.

### 4. Pre-change snapshots
- Create a recovery checkpoint before every meaningful seed/kernel/driver/configuration mutation.
- Later, extend this to component-level StateWeave snapshots so individual subsystems can be reverted without discarding unrelated learning.

### 5. Evidence-driven automatic rollback
Rollback must be deterministic, not random. Trigger rollback on evidence such as:
- repeated boot failure;
- failure to reach the expected healthy runtime state;
- critical service failure;
- catastrophic GUI/runtime regression when GUI availability is expected;
- loss of required hardware/runtime capabilities after a change;
- repeated crash/restart loops;
- health score falling below the accepted gate.

On failure:
1. freeze further adaptation;
2. capture/log the failed state;
3. quarantine the failed candidate/change;
4. restore the affected component when safe and supported;
5. otherwise switch back to LKG;
6. boot and re-run health validation;
7. report recovery state.

### 6. Change journal and quarantine
Every autonomous mutation must record:
- before state/version;
- requested or autonomous change;
- candidate state/version;
- validation result;
- promotion or rollback result.

Failed candidates are preserved for diagnosis but may not silently reactivate or promote themselves.

## GitHub remote recovery control plane

GitHub is a remote recovery trigger, not an unrestricted remote shell.

A protected desired-state instruction should support at least:
- stay-current;
- rollback to previous proven state;
- rollback to Last Known Good;
- rollback to a specifically trusted seed/version.

Example conceptual command:

```yaml
node: hopper
action: rollback
target: last-known-good
command-id: 184
expires: 30m
```

### Remote-trigger safeguards
- authenticate/sign recovery instructions;
- monotonically unique command IDs or equivalent replay protection;
- command expiration;
- protected repository/workflow permissions;
- node targeting;
- no arbitrary shell-command field;
- local State Guardian retains final authority;
- record acknowledgement/result back to the project state/status path when available.

The intended user-facing control is a GitHub workflow such as **Aurum Emergency Rollback**, allowing a trusted operator to select a node and recovery target from a phone or browser.

## Snapshot policy

Use multiple checkpoint types:
- mandatory checkpoint immediately before meaningful mutation;
- checkpoint after a candidate becomes proven healthy;
- periodic lightweight healthy-state checkpoints;
- optional low-cost randomized healthy-state samples to improve recovery coverage.

Randomness may influence when an additional snapshot is taken. **Rollback decisions themselves must never be random.**

## Promotion flow

`proven state -> snapshot -> candidate change -> boot/test -> health gate -> promote -> new LKG`

Failure flow:

`candidate failure -> freeze -> capture -> quarantine -> component rollback or LKG rollback -> boot/test -> report`

## Planned implementation order

### Phase 1 — minimal survival layer
1. A/B seed slots.
2. LKG metadata/pointer.
3. protected State Guardian/watchdog.
4. pre-change snapshot hook.
5. boot/runtime health gate.
6. automatic rollback.
7. mutation journal/quarantine.
8. GitHub desired-state rollback trigger.

### Phase 2 — finer recovery
- subsystem-level StateWeave rollback;
- partial driver/kernel/config restoration;
- richer health scoring and root-cause attribution;
- periodic healthy snapshots.

### Phase 3 — canary and fleet behavior
- validate risky changes on an experimental node before production/core nodes;
- staged rollout by node;
- cross-node recovery evidence without allowing one compromised node to overwrite another's LKG.

## Design principle

**Adapt aggressively. Commit conservatively. Recover automatically.**
