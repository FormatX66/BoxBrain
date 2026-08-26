# Future Branch — Current Canonical Workflow

Future Branch is the operating spine for Aurum/BoxBrain. It is not only prediction. It combines state awareness, anticipatory branching, execution routing, uncertainty scaling, unattended preparation, safety, and proof.

## Canonical loop

```text
observe verified state
  -> separate facts / assumptions / unknowns / authority
  -> expand short/generic prompt into likely required outcome from live context
  -> execute the safe prefix shared by plausible intents before asking
  -> infer likely goal + likely next questions
  -> fan out useful futures:
       success / failure / likely causes / recovery / next actions / alternates
  -> persist the chat/process tree:
       keep sibling machine lanes active behind one human focus path
       pin concepts / decisions / evidence / blockers to durable nodes
       merge results with source provenance instead of erasing branches
  -> score uncertainty:
       Reality Gap
       Surprise Reserve
       stacked gaps: context, topology, capability, runtime, evidence,
                     freshness, concurrency, resources, recovery proof,
                     human interpretation
  -> increase preparation effort when gap stack is high
  -> expected-information-value gate:
       pre-run safe bounded work when learning/value exceeds cost/risk
  -> unattended precompute while human unavailable:
       artifact / target identity / runtime probes / service probes / dry run /
       failure simulations / alternate routes / pass+fail paths / recovery /
       evidence contract / next-boundary packet
  -> resolve execution routes:
       direct-local
       connected capability
       authorized runner
       workspace handoff
       human-assisted
  -> real physical/authority boundary stops effect only, not preparation
  -> preserve Last Known Good / Guardian invariants
  -> execute only with valid authority and fresh state
  -> verify independently: ran != worked
  -> collapse successful branches
  -> journal/quarantine failures
  -> learn surprises into reusable gaps/invariants
  -> refresh the future tree
```

## Mandatory invariants

1. Anticipate aggressively; commit conservatively.
2. Preparation is not execution; route choice is not authority.
3. Human/physical blockers stop the effect, not Future Branch analysis.
4. Keep success, failure, recovery, and next-step branches warm across boundaries.
5. Human route is valid but should not be the automatic escape hatch.
6. High Reality Gap or stacked uncertainty receives more compute, wider diagnostics, and deeper lookahead.
7. Always reserve probability for unknown-unknowns. Repeated surprises increase the reserve and lower confidence.
8. Multiple moderate gaps compound; do not rank only the single largest risk.
9. Use human time for adaptability, judgment, subjective choices, and physical action; use machine time for persistence, exhaustive testing, verification, and unattended precompute.
10. Never destroy Last Known Good for speculation. State Guardian safety wins over branch ranking.
11. Freshness is part of validity: target, artifact, evidence, authority, environment, or route changes invalidate stale prepared state.
12. Retry only when state/evidence/implementation/environment/dependency/hypothesis/authority changed.
13. `ran` != `worked`; promotion != success. Verification closes the loop.
14. Every surprise should become reusable learning at the earliest shared layer, not a one-off workaround.
15. Before replying or escalating, ask:
    - what happens next if this succeeds?
    - what happens next if it fails?
    - what could surprise us here?
    - what can be safely prepared now?
    - what execution route avoids unnecessary human work?
    - what evidence proves success?
16. A short or generic prompt is direction, not a blocker. Infer likely intent from
    verified state, recent work, project contracts, and calibrated human-input
    branches. Execute shared safe work first; act on a strong safe leader; ask only
    after useful preparation is exhausted or a real boundary remains. Inferred
    intent never grants authority.
17. Human focus is linear; machine work is not. Changing the visible chat path must
    not collapse sibling processes, pinned concepts, evidence, blockers, or merge
    provenance. The process tree records concurrency but never grants authority.

## Human availability behavior

Human availability is a soft prior, never authority. A likely unavailable human means keep safe machine work moving. A likely hardware-available window means surface the single highest-value physical action with pass/fail/recovery branches already prepared.

## Unattended precompute

When a likely future physical action is known, use human-unavailable time to reduce uncertainty until the next true physical/authority boundary. Produce a compact physical-session packet rather than starting diagnosis when the human returns.

## Relationship to implementation

Canonical supporting pieces:
- `Architecture/FutureBranch.md` — original architecture and branch families.
- [ChatProcessTree.md](ChatProcessTree.md) — durable conversation/process lanes and merge provenance.
- `Architecture/ExecutionRoutes.md` — route ranking.
- `Prompts/FutureBranchSeed.txt` — portable compact seed.
- `Projects/Aurum/Experiments/speculative_feasibility.py` — expected information value.
- `Projects/Aurum/Experiments/execution_route.py` — route ranking implementation.
- `Projects/Aurum/Experiments/human_availability.py` — human availability prior.
- `Projects/Aurum/Experiments/surprise_budget.py` — unknown-unknown reserve.
- `Projects/Aurum/Experiments/reality_gap.py` — concept-to-reality uncertainty scaling.
- `Projects/Aurum/Experiments/gap_stack.py` — compounded uncertainty gaps.
- `Projects/Aurum/Experiments/unattended_precompute.py` — night-before / human-unavailable preparation.
- `Projects/Aurum/Experiments/chat_process_tree.py` — concurrent process/concept tree implementation.

This document is the reconciliation point. If later Future Branch work changes behavior, update this spine and its regression test in the same change.

> Human chooses direction; machine clears the field.
