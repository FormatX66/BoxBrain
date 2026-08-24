# Future Branch Human Calibration and Depth Policy

**Status:** Active experimental policy supporting `FUTURE_BRANCH.md`

Future Branch should learn from ordinary human interaction, not only machine outcomes. Early in training, useful questions are part of the prediction system because a small clarification can collapse many low-confidence futures into a smaller, more valuable branch field.

## Ask questions when they buy information

Question count should follow the **shape of uncertainty**, not a fixed quota.

Useful early-training heuristic:

- several plausible branches clustered around ~20–35% may justify **up to three short questions**;
- two competitive branches around ~40–60% may justify **about two questions**;
- one dominant branch around ~70%+ usually justifies **one discriminating question at most**;
- when one branch is very high, prefer a question that can **confirm or falsify the leader** rather than simply asking the obvious top choice back to the user;
- ask zero questions when the branch is already clear, safe, cheap, and linear enough that preparation is more valuable than interruption.

Aurum should ask a short calibration question when one or more of these are true:

- the leading future is weak or several branches are close in probability;
- the wrong speculative branch would consume meaningful compute, storage, network, or human attention;
- a user preference materially changes what should be prepared next;
- the answer will improve future predictions beyond the immediate turn.

Do **not** interrupt a strong, low-risk, linear future merely to ask a question. If the likely path is already clear and safe, prepare it.

Early training may ask more often. As calibration improves, questions should become rarer and more targeted.

## Human confidence feedback

When useful, give the human a small natural signal describing how expected the resolved branch was. The purpose is to help the person understand whether useful work was probably already warm or whether the system has to fan out and recompute.

Example tones, not fixed scripts:

- very high confidence: `I had that path warm already.`
- expected: `That was one of the directions I was expecting.`
- plausible but not leading: `That was possible, but it was not one of my strongest branches.`
- surprising: `That came from outside my leading branches, so I am recalculating around it.`

Do not use these as bragging. They are latency/compute cues and calibration evidence.

Trivial surface features such as spelling mistakes, punctuation, or wording quirks do not count as meaningful Future Branch wins.

### Deliberately vary the feedback sample

During early training, do not use the same confidence wording every time. Mix the feedback style and frequency enough to learn which cues are useful, distracting, or misleading to the human.

Vary across:

- warm/expected/plausible/surprising branch classes;
- terse vs slightly explanatory wording;
- explicit compute/latency implication vs simple confidence wording;
- some meaningful turns with no confidence cue at all.

The variation is part of the calibration experiment. It should later converge toward the feedback style that best helps the user judge likely wait/recompute cost without becoming noisy.

### Avoid the observer effect

During natural calibration, do not normally reveal a specific prediction **before** the human supplies the next intent, because doing so can steer the human toward or away from that branch and corrupt the training evidence.

Prefer confidence feedback immediately **after** the branch resolves. Reveal a prediction early only when the information itself is useful for a decision, safety, consent, cost, or latency expectation.

## Adaptive breadth and depth — everything all at once

Future Branch should not choose between breadth and depth. Use both:

- **breadth:** keep many plausible futures shallow/warm in RAM/Slush when resources allow;
- **depth:** push the highest-probability, highly linear branches much farther ahead;
- **pruning:** cool, compress, or discard branches as evidence lowers expected value;
- **reallocation:** immediately reuse reclaimed CPU/RAM/Slush for the next highest-value futures.

Lookahead depth is not fixed at one or two steps. Two is only a normal minimum preparation horizon, not a ceiling.

Depth should increase when **probability**, **linearity**, and **resource headroom** are high. A branch is linear when each next step follows predictably from the prior one with few meaningful forks.

Conceptually:

`depth pressure = probability × linearity × expected user-time saved × preparation leverage × resource headroom / speculative cost`

When a branch is very high-probability and highly linear, preparation should continue **until the first reasonable boundary**, not until an arbitrary step count. Reasonable boundaries include:

- foreground latency/responsiveness reserve;
- reclaimable CPU/GPU budget;
- RAM/Slush reserve;
- storage free-space/write-endurance budget;
- network/privacy budget;
- dependency boundary;
- safety/permission/credential/preference boundary;
- destructive/irreversible/physical boundary.

Forky, uncertain, expensive, or privacy-sensitive branches remain shallow even when plausible.

## Balance apparent waste against compounded efficiency

Do not optimize only for the next resolved branch. Some speculative work that looks wasted at first can produce durable value later.

Evaluate speculation on two horizons:

- **immediate value** — human wait removed if the predicted branch becomes active now;
- **compounding value** — reusable partial state, cached artifacts, improved prediction calibration, assumptions exposed early, future errors avoided, and work that can be shared by neighboring branches.

A near-term miss is therefore not automatically total waste. Track both **gross speculative work** and **net waste after reusable/learning/error-avoidance value**.

This does not justify unlimited computation. Speculation should continue only while its expected long-horizon return plausibly exceeds its costs in compute, energy, RAM/Slush pressure, storage writes, network use, privacy exposure, and foreground interference.

The desired optimization target is not minimum speculative work. It is **minimum total human/system cost over time**.

## Training loop

1. Maintain a broad ranked field of likely futures.
2. Derive a question budget from the uncertainty shape.
3. Ask only questions whose information gain is worth the interruption.
4. Re-rank branches from the answer.
5. Keep many plausible branches warm shallowly when resources permit.
6. Deepen hot linear branches until a real or resource boundary.
7. Let natural user intent resolve the branch when possible without exposing predictions first.
8. Give varied lightweight confidence feedback after resolution when useful.
9. Score whether the prediction was useful and whether the implied work was actually prepared/executed.
10. Score immediate benefit separately from compounded reuse/learning/error-avoidance value.
11. Reallocate speculative resources from cooled/missed branches to newly promoted futures.
12. Reduce question frequency as calibration improves.

The goal is not to predict the user's wording. The goal is to predict enough of the user's **intent and next useful state** that the machine can reduce waiting while remaining non-interfering.
