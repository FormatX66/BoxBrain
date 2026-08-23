# Aurum Seed Recovery Architecture

Status: **Mandatory base-seed requirement**

## Core invariant

> No new state may destroy the last proven working state.

Aurum may experiment and adapt aggressively, but promotion of a new seed/state must be conservative and reversible.

## Genetics/regrowth model

Recovery is not primarily a conventional image-restore or sequential-version process. GitHub carries the **current Aurum genetics**; a viable seed carries a protected **Reseed Germ** that can fetch those genetics and regrow a hardware-specific candidate beside the currently viable organism.

Aurum must therefore satisfy both invariants:

1. **No new state may destroy the last proven working state.**
2. **Any viable germ-bearing seed must be able to regrow directly into the current trusted genetics without replaying every intermediate generation.**

A/B slots and Last Known Good are local survival mechanisms that keep the machine alive while regrowth occurs. They are not a requirement to treat Aurum as a sequence of frozen release images.

The canonical genetics/germ contract is defined in `docs/architecture/RESEED_GENETICS_ARCHITECTURE.md`.

## Required base-seed protections

### 1. A/B seed slots
- Never overwrite the currently proven bootable seed in place.
- Build or install a candidate into the inactive slot.
- Promote the candidate only after required boot and health validation succeeds.
- Preserve the prior proven slot until the new candidate becomes trusted.
- Treat the inactive slot as a growth chamber for genetics-derived candidates, not as a conventional update partition.

### 2. Last Known Good (LKG)
- Maintain an explicit LKG pointer/state independent of the active candidate.
- A candidate cannot become LKG until it passes the defined health gate.
- LKG must remain recoverable if the active seed is corrupt, incomplete, or non-booting.
- LKG is a local survival anchor; it does not define the current Aurum genetics and does not need to be the newest genetics.

### 3. Independent State Guardian / watchdog
- Recovery logic must be smaller, more conservative, and less mutable than the adaptive seed.
- Normal Aurum adaptation must not be allowed to casually rewrite or disable its recovery mechanism.
- The Guardian has final local authority to reject an unhealthy candidate and restore LKG.
- The protected Reseed Germ and Guardian must remain usable even when the adaptive/user-facing Aurum layer is damaged.

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
7. report recovery state;
8. when appropriate, use the protected germ to regrow a fresh candidate from current trusted genetics instead of repeatedly repairing a corrupted phenotype in place.

### 6. Change journal and quarantine
Every autonomous mutation must record:
- before state/version;
- requested or autonomous change;
- candidate state/version;
- resolved genetics commit SHA and manifest identity when regrowth is involved;
- validation result;
- promotion or rollback result.

Failed candidates are preserved for diagnosis but may not silently reactivate or promote themselves.

## GitHub remote recovery control plane

GitHub is both the durable genetics source and a remote recovery trigger surface; it is not an unrestricted remote shell.

A protected desired-state instruction should support at least:
- stay-current;
- reseed/regrow from current trusted genetics;
- reseed/regrow from a specifically trusted commit;
- rollback to previous proven local state;
- rollback to Last Known Good.

Example conceptual command:

```yaml
node: hopper
action: reseed
target: current-trusted-genetics
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
- resolve an immutable genetics commit before growth;
- local State Guardian retains final authority;
- record acknowledgement/result back to the project state/status path when available.

The intended user-facing control is a GitHub workflow such as **Aurum Emergency Recovery**, allowing a trusted operator to select a node and either regrow current genetics or select a local/historical recovery target from a phone or browser.

## Snapshot policy

Use multiple checkpoint types:
- mandatory checkpoint immediately before meaningful mutation;
- checkpoint after a candidate becomes proven healthy;
- periodic lightweight healthy-state checkpoints;
- optional low-cost randomized healthy-state samples to improve recovery coverage.

Randomness may influence when an additional snapshot is taken. **Rollback decisions themselves must never be random.**

## Promotion flow

`proven local state -> snapshot -> resolve genetics -> grow candidate -> boot/test -> health gate -> promote -> new LKG`

Failure flow:

`candidate failure -> freeze -> capture -> quarantine -> component/LKG rollback -> boot/test -> optionally regrow fresh candidate -> report`

## Planned implementation order

### Phase 1 — minimal survival layer
1. protected Reseed Germ with a stable genetics manifest/protocol;
2. A/B seed slots;
3. LKG metadata/pointer;
4. protected State Guardian/watchdog;
5. candidate-only genetics staging and pre-change snapshot hook;
6. boot/runtime health gate;
7. automatic rollback;
8. mutation journal/quarantine;
9. GitHub desired-state reseed/rollback trigger.

### Phase 2 — finer recovery
- subsystem-level StateWeave rollback;
- partial driver/kernel/config restoration;
- richer health scoring and root-cause attribution;
- periodic healthy snapshots;
- signed genetics manifests/protected-ref verification.

### Phase 3 — canary and fleet behavior
- validate risky changes on an experimental node before production/core nodes;
- staged rollout by node;
- cross-node recovery evidence without allowing one compromised node to overwrite another's LKG.

## Design principle

**Git stores the genetics. Seeds carry the germ. Adapt aggressively. Commit conservatively. Regrow or recover automatically.**
