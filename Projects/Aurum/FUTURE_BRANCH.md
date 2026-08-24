# Future Branch

**Status:** Core Aurum operating principle

Future Branch means the system should not wait for the current step to finish before thinking about what is likely to happen next. It should maintain a small, ranked set of likely future states, prepare the most useful next steps in advance, and use new evidence to prune, correct, or deepen those branches.

## Core rule

> Be one or two useful steps ahead without crossing a real dependency, safety, authorization, or physical boundary early.

A dependency may block execution, but it should not block preparation.

If an ISO must exist before a disk can be flashed, Aurum cannot flash early. It can still prepare the flash tool, target-safety checks, readback verification, boot-proof collection, likely failure diagnostics, rollback path, and the step after a successful boot while the ISO is still building.

## Branch set

For every meaningful live gate, maintain at least:

1. **Success branch** — what becomes possible if the current gate passes.
2. **Likely failure branches** — the most probable and consequential ways the gate may fail.
3. **Recovery branch** — how to return to a proven state when a failure affects active state.
4. **Next-capability branch** — what useful work should begin after the current milestone succeeds.

Do not prepare every imaginable branch. Rank branches by expected value.

A practical priority score is conceptually:

`probability × impact × user-time-saved × preparation-leverage / cost`

High-probability, high-impact, cheap-to-prepare branches go first. Low-probability expensive speculation stays shallow or is discarded.

## Future Branch loop

`Current Proven State`

→ observe current evidence

→ generate plausible next success/failure states

→ rank by probability, impact, cost, and user latency saved

→ prepare safe downstream artifacts and diagnostics in parallel

→ execute only branches whose prerequisites and permissions are satisfied

→ compare predicted branch with actual result

→ correct assumptions and prune wrong branches

→ deepen the branch supported by evidence

→ verify the resulting state

→ make the new proven state the basis for the next Future Branch set

## Self-correction value

Future Branch is not only prefetching. It is an error-discovery mechanism.

By constructing likely next states before they are needed, Aurum can expose its own hidden assumptions early. A prepared flash path may reveal that artifact identity is not pinned. A prepared rollback path may reveal that a trial clears metadata earlier than assumed. A prepared physical test may reveal that evidence collection was never embedded in the image.

The system should treat these discoveries as useful evidence, repair the assumption, and regenerate the affected branch before the user reaches it.

The intended effect is:

- fewer user-visible dead ends;
- less waiting between dependent operations;
- fewer repeated instructions;
- fewer "now what?" interactions;
- earlier discovery of bad assumptions;
- faster recovery when the actual result differs from prediction;
- more useful use of idle compute, RAM, storage, CI capacity, and preparation time.

## Execution boundary

Future Branch may **think ahead freely** and **prepare ahead aggressively**, but it may **act ahead only when confidence, dependency, safety, and permission allow it**.

Speculative work must remain:

- reversible or disposable;
- isolated from Last Known Good state;
- preemptible by foreground work;
- bounded by compute, memory, storage-write, network, privacy, and thermal budgets;
- clearly distinguished from verified active state.

No speculative branch may silently become production state.

## Operator behavior

When operating Aurum or any multi-step project:

- do not stop at the current command boundary;
- ask what the operator is most likely to report next if it works;
- ask what the operator is most likely to report next if it fails;
- prepare the highest-value responses to both before waiting;
- keep at least the next one or two useful stages ready when safe;
- use actual evidence to re-rank branches continuously;
- if a branch proves wrong, correct it rather than defending the original assumption;
- notify the operator only when a real human boundary is reached or a meaningful verified result is available.

## Relationship to other Aurum principles

Future Branch complements:

- **Whole-State Synthesis** — synthesize coherent future candidate states rather than isolated lines/tasks.
- **StateWeave** — represent and preserve candidate/proven states and their relationships.
- **Slush memory** — hold reclaimable speculative work and prepared state.
- **Adaptive scheduling** — consume idle capacity while preserving foreground headroom.
- **A/B + LKG + State Guardian** — keep speculative/candidate work from destroying the last proven state.

Aurum's desired operating posture is therefore not **WAITING FOR COMMAND** but **ANTICIPATING, PREPARED, EVIDENCE-CORRECTING, AND NON-INTERFERING**.
