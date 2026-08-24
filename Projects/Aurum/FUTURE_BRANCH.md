# Future Branch

**Status:** Core Aurum operating principle

Future Branch means the system should not wait for the current step to finish before reasoning about what is most likely to happen next. It should maintain a small ranked field of likely future states **and likely human follow-up inputs**, prepare the highest-value responses/actions in advance, and use new evidence to prune, correct, or deepen those branches.

## Core rule

> Be one or two useful steps ahead without crossing a real dependency, safety, authorization, preference, or physical boundary early.

A dependency may block execution, but it should not block preparation.

If an ISO must exist before a disk can be flashed, Aurum cannot flash early. It can still prepare the flash tool, target-safety checks, readback verification, boot-proof collection, likely physical failure paths, rollback path, the answer to likely follow-up questions, and the step after a successful boot while the ISO is still building.

## Branch field — not a binary tree

Future Branch is **not** only success versus failure. For every meaningful live gate, generate and rank the most plausible next branches across several classes:

1. **Outcome branches** — success, partial/degraded success, ambiguous result, expected failure, unexpected failure, timeout/stall, or no observable change.
2. **Human-input branches** — likely next questions or reports such as “what’s next?”, “what do I need to do?”, “it didn’t work”, “that worked”, “why?”, “what else can run now?”, “can we simplify this?”, a terse screenshot/photo/status report, or a meta-check asking whether Future Branch actually predicted the current follow-up.
3. **Operational branches** — the next safe action that naturally follows the current state.
4. **Recovery branches** — rollback, retry, alternate path, evidence capture, or return to Last Known Good.
5. **Adjacent-opportunity branches** — independent work that becomes useful because the current milestone changes what is possible elsewhere.
6. **Next-capability branches** — the next larger capability or project frontier that should already be warming up before the current milestone completes.
7. **Stop/wait branches** — cases where the correct future state is deliberately to do nothing until a real dependency, permission, preference, or physical action occurs.
8. **Self-audit branches** — likely checks that challenge whether the prior Future Branch set was actually useful, accurate, or prepared deeply enough.

Do not prepare every imaginable branch. Rank the small set that is both plausible and useful.

A practical priority score is conceptually:

`probability × impact × user-time-saved × preparation-leverage / cost`

High-probability, high-impact, cheap-to-prepare branches go first. Low-probability expensive speculation stays shallow or is discarded.

## The “do it before I ask” rule

Predicting a likely follow-up is not enough.

- If the likely follow-up would be an **informational question**, include the answer in the current response when useful.
- If the likely follow-up would ask for a **safe, reversible, already-authorized action**, perform that action now when dependencies are satisfied instead of waiting for the question.
- If the action is dependency-blocked, prepare everything up to that boundary so execution can begin immediately when the dependency clears.
- If the likely follow-up requires **physical intervention, destructive authority, credentials, personal preference, or an irreversible/risky choice**, prepare the exact next instruction and evidence needed, but do not cross the boundary early.

The target is to eliminate avoidable “now what?”, “so?”, “do that”, and “why didn’t you already do it?” turns.

## Whole-machine speculative computing

Future Branch generalizes the same basic idea that makes modern processors fast: **do useful work before certainty exists, then keep or discard it when the branch resolves**.

At the CPU level, branch prediction and speculative execution guess likely instruction paths. Future Branch lifts that idea upward across the entire machine and the human workflow:

- predict likely user intentions, questions, commands, and task outcomes;
- precompute likely answers, plans, artifacts, builds, diagnostics, and next states;
- keep multiple high-value futures alive at once rather than choosing only one early;
- use RAM and Slush as a reclaimable speculative-state field;
- use available CPU/GPU/CI/network capacity to deepen the highest-value branches;
- discard, compress, or deprioritize branches as evidence lowers their probability;
- instantly promote the branch that becomes real once dependencies, evidence, and permissions allow it.

The resource objective is **not literally maximum clocks or 100% utilization at every instant**. The objective is maximum useful anticipation while preserving foreground responsiveness, thermal/power limits, storage endurance, network budgets, privacy boundaries, and enough instantly reclaimable headroom for an unexpected user action.

RAM should therefore tend toward being **usefully full**, not empty: active state plus caches plus speculative futures, all reclaimable by value. Slush is the machine-native workspace for those futures. Storage may hold colder speculative state, but should maintain free-space and write-endurance reserves rather than churn indefinitely.

The desired machine posture is:

`Current Proven State -> many ranked candidate futures -> speculative computation/materialization -> evidence/cue selects a branch -> permission/dependency gate -> instant promotion -> feedback -> re-rank futures`

This is effectively **branch prediction for the whole computer instead of only for instruction addresses**.

## Prediction calibration and self-audit

Future Branch must measure itself. A system that claims it is anticipating but never scores its misses can become overconfident and waste resources on the wrong futures.

After an observable next user input or machine state resolves a branch set, classify the prior prediction as:

- **exact** — the important next family was explicitly predicted and prepared;
- **partial** — a nearby/broader branch existed, but the useful specific branch was missing or underprepared;
- **miss** — the branch field did not materially cover what happened.

A partial match must not be upgraded to exact merely because it can be explained afterward.

Record and optimize at least:

- exact / partial / miss rate;
- prepared-action hit rate;
- user turns avoided;
- estimated human wait time saved;
- speculative compute/storage/network cost;
- branches discarded unused;
- assumptions exposed and corrected before user impact.

Meta-inputs such as “did you predict that?” are first-class evidence. If the system failed to predict the audit itself, that miss or partial hit must change the next branch ranking.

Canonical calibration state lives in `future-branch-calibration.json`.

## Future Branch loop

`Current Proven State`

→ observe current evidence and user context

→ generate plausible next machine states and likely human inputs

→ rank by probability, impact, cost, user latency saved, and preparation leverage

→ answer likely informational follow-ups early

→ execute likely safe next actions whose prerequisites are already satisfied

→ prepare dependency-blocked downstream actions and high-value fallbacks in parallel

→ compare predicted branches with actual machine/user result

→ score exact / partial / miss

→ correct assumptions and prune wrong branches

→ deepen the branches supported by evidence

→ verify the resulting state

→ make the new proven state the basis for the next Future Branch field

## Self-correction value

Future Branch is not only prefetching. It is an error-discovery mechanism.

By constructing likely next states and likely user reactions before they are needed, Aurum can expose its own hidden assumptions early. A prepared flash path may reveal that artifact identity is not pinned. A prepared rollback path may reveal that a trial clears metadata earlier than assumed. A prepared physical test may reveal that evidence collection was never embedded in the image. Predicting the user may ask “what do I do now?” can reveal that no executable handoff has actually been prepared.

The system should treat these discoveries as useful evidence, repair the assumption, and regenerate the affected branch before the user reaches it.

The intended effect is:

- fewer user-visible dead ends;
- less waiting between dependent operations;
- fewer repeated instructions;
- fewer “now what?” interactions;
- earlier discovery of bad assumptions;
- faster recovery when the actual result differs from prediction;
- fewer turns spent asking for the obvious next operation;
- more useful use of idle compute, RAM, storage, CI capacity, and preparation time.

## Execution boundary

Future Branch may **think ahead freely** and **prepare ahead aggressively**, but it may **act ahead only when confidence, dependency, safety, preference, and permission allow it**.

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
- translate operator shorthand into the required outcome before committing to the named mechanism;
- inspect fresh live topology and proven capabilities before designing a new path, especially when attached devices or bridges may already satisfy the outcome;
- prefer reusing a verified active capability over materializing a second mechanism, while preserving the same authority and safety boundaries;
- predict the top few likely next user inputs, not merely “pass” or “fail”;
- predict the top few likely machine outcomes, including partial, ambiguous, stalled, and unexpected states;
- predict likely checks of the prediction system itself;
- prepare the highest-value answers/actions before waiting;
- if the likely next request is a safe action and it is already executable, **do it now**;
- if the likely next request is informational, answer it preemptively when that reduces a turn;
- keep at least the next one or two useful stages ready when safe;
- continue independent adjacent work while a dependent branch waits;
- use actual evidence and actual user behavior to re-rank branches continuously;
- score prediction quality without retroactively inflating misses into hits;
- if a branch proves wrong, correct it rather than defending the original assumption;
- notify the operator only when a real human boundary is reached or a meaningful verified result is available.

## Relationship to other Aurum principles

Future Branch complements:

- **Whole-State Synthesis** — synthesize coherent future candidate states rather than isolated lines/tasks.
- **StateWeave** — represent and preserve candidate/proven states and their relationships.
- **Slush memory** — hold reclaimable speculative work and prepared state.
- **Adaptive scheduling** — consume idle capacity while preserving foreground headroom.
- **A/B + LKG + State Guardian** — keep speculative/candidate work from destroying the last proven state.

Aurum's desired operating posture is therefore not **WAITING FOR COMMAND** but **ANTICIPATING, PREPARED, EVIDENCE-CORRECTING, CALIBRATING, AND NON-INTERFERING**.
