# Future Branch Architecture

> **Current reconciled operating spine:** [FutureBranchCurrent.md](FutureBranchCurrent.md). This document preserves the original architecture and branch-family rationale; the current canonical workflow must include later execution-routing, Reality Gap, Surprise Reserve, Gap Stack, human-availability, expected-information-value, and unattended-precompute behavior.

Future Branch is the common decision primitive for BoxBrain/Aurum when more
than one plausible future remains. It extends the existing state-first
execution policy without replacing it.

> Anticipate aggressively; commit conservatively.

## Universal loop

```text
intent / observation
    -> current verified state
    -> unresolved delta or question
    -> small set of plausible future branches
    -> score each branch independently by:
         confidence
         evidence quality
         risk
         cost
         reversibility
         authority
         freshness / expiry
    -> prepare safe/reversible branches where useful
    -> promote at most one branch when its threshold is crossed
       OR wait for more evidence when branches remain ambiguous
    -> execute only through the existing safety/policy boundary
    -> verify resulting state
    -> collapse stale branches
    -> rollback when required
    -> quarantine failed candidates
```

A Future Branch is not hidden chain-of-thought and does not require storing
private reasoning. The auditable representation is the branch state, evidence
references, scores/inputs, safety properties, decision, and verification result.

## Branch contract

A branch should be able to represent:

- stable branch id;
- proposed state or action;
- confidence;
- risk;
- cost;
- reversibility (`full`, `partial`, `none`);
- evidence references and evidence quality;
- status (`warm`, `promoted`, `rejected`, `quarantined`, `expired`);
- authorization requirement and current authorization state;
- optional expiry;
- optional rollback target;
- whether the branch is Last Known Good.

Confidence, proof, authority, and safety are separate dimensions. A branch can
be likely but unsafe, authorized but poorly supported, safe but not yet useful,
or well-evidenced but expired.

## Global invariants

1. **Never destroy Last Known Good for a speculative future.** LKG remains an
   explicit competing branch until a newly promoted state is independently
   verified and accepted as the next proven state.
2. **Preparation is not execution.** Safe work may be staged early; destructive
   or high-impact effects wait for the required evidence and authority.
3. **Ambiguous ties wait.** Do not manufacture certainty when two plausible
   futures are effectively tied.
4. **Failures collapse branches.** Failed candidates are journaled and
   quarantined instead of being blindly retried with unchanged evidence.
5. **Fresh evidence changes the tree.** A retry or renewed branch is justified
   only when state, evidence, implementation, environment, dependency,
   hypothesis, or authority changed.
6. **Existing policy remains sovereign.** Future Branch never bypasses target
   identity, permission, emergency stop, privacy, destructive-action,
   credential, or other established gates.
7. **Branch count is bounded.** Prefer a small set of materially different
   futures rather than an unbounded speculative tree.
8. **Verification closes the loop.** Promotion is not success. The resulting
   state must still be measured and verified.

## Three universal branch families

### Intent Branching

Question: **What is the user probably trying to accomplish?**

Keep multiple short-lived intent hypotheses when evidence is incomplete.
Prepare only safe/reversible prerequisites until intent is strong enough.

Examples:

- USB media appears during seed work: inspect, identify, locate latest trusted
  seed, and prepare LKG metadata before assuming the user wants the drive erased.
- GUI adaptation: maintain multiple workflow preference hypotheses rather than
  permanently changing the interface from one observation.
- Identity/session confidence: maintain competing identity hypotheses without
  weakening the existing privilege threshold.
- TypeTriX: preserve literal text and plausible corrections simultaneously
  until subsequent typing collapses the ambiguity.

### State Branching

Question: **What state should the machine become next?**

Examples:

- A/B seed candidate vs Last Known Good vs wait-for-health vs rollback.
- kernel/driver canary vs current proven implementation vs alternate candidate.
- USB/Ethernet/Wi-Fi/Bluetooth transport alternatives.
- StateWeave candidate transitions.
- deployment candidate vs current release vs rollback.

### Diagnostic Branching

Question: **Which explanation of the observed problem is most likely?**

Examples:

- power / cable / transport / driver / firmware / hardware failure;
- DNS / TLS / routing / container / application regression;
- CI configuration / dependency / quota / authorization / code regression;
- failed seed / storage media / architecture mismatch / network prerequisite.

Prefer cheap evidence-producing tests that eliminate branches before promoting a
repair.

## Project applications

### Seed, Tiny Seed, reseed and recovery

Use Future Branch directly with the A/B + LKG + State Guardian architecture.
Candidate state, current LKG, rollback, offline recovery, remote desired-state,
and wait-for-health remain distinct branches. A signed GitHub recovery input is
evidence/constraint on a branch; it is not permission for an unverified
mutation to destroy LKG.

### Adaptive kernel and drivers

Keep the current proven path warm while a candidate is tested in a bounded
canary. Branches should capture hardware evidence, boot/health evidence,
performance evidence, regression evidence, and rollback availability.

### StateWeave

StateWeave records the state graph and evidence history. Future Branch chooses
which candidate transition deserves promotion. Store branch ids, evidence refs,
decision inputs, branch status, resulting verified state, and rollback lineage.

### Mesh and transport

Rank available transports from fresh reachability, identity, trust, latency,
and capability evidence. Preparing an alternate transport must not silently
broaden trust.

### Hardware diagnosis

Represent competing causes as branches and order tests by information gained,
risk, and cost. A repair is a promoted branch only after the diagnostic tree has
sufficient evidence.

### GUI and workflow adaptation

Learn gradually. Keep multiple interface/workflow models warm and use repeated
behavior as evidence. Preserve easy switching and rollback to familiar layouts.

### Identity and authentication

Future Branch may maintain confidence-ranked identity/session hypotheses but
must never lower required authentication or authorization thresholds.

### Dashboard/status

Expose useful Future Branch state where appropriate: current verified state,
likely next state, warm alternatives, blockers, evidence freshness, rollback,
and confidence. Never present speculation as verified fact.

### CI, deployments, websites and cluster operations

Branch on failure class and repair path. Read-only diagnostics, cached verified
state, rollback, alternate authorized route, bounded retry-after, and wait are
valid branches. An unchanged failed command is not a new future.

### Social and content workflows

Use Future Branch for drafts, timing, response intent, and likely next content,
but posting or other external side effects remain behind the appropriate user
approval/policy boundary.

## Relationship to the State Guardian

Future Branch proposes and ranks candidate futures.

The State Guardian is independent and enforces invariants, health gates,
protected LKG, rollback, and quarantine. Future Branch cannot vote the Guardian
out of existence. If the promoted candidate fails verification, Guardian
recovery wins.

## Implementation ownership

BoxBrain owns this cross-project architecture and vocabulary.

BrainConnect owns the first reusable Aurum controller implementation. Its
platform-neutral Future Branch primitive is intentionally independent of
transport, model, database, and UI dependencies so other Aurum components can
reuse the contract without bypassing their safety boundaries.

TypeTriX owns its text-intent specialization and can evolve independently while
preserving the same general concepts of warm alternatives, evidence,
ambiguity restraint, and conservative promotion.

Each future project should reuse the shared semantics instead of inventing a
new incompatible branch model.
