# Future Branch Human Calibration and Depth Policy

**Status:** Active experimental policy supporting `FUTURE_BRANCH.md`

Future Branch should learn from ordinary human interaction, not only machine outcomes. Early in training, useful questions are part of the prediction system because a small clarification can collapse many low-confidence futures into a smaller, more valuable branch field.

## Ask questions when they buy information

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

### Avoid the observer effect

During natural calibration, do not normally reveal a specific prediction **before** the human supplies the next intent, because doing so can steer the human toward or away from that branch and corrupt the training evidence.

Prefer confidence feedback immediately **after** the branch resolves. Reveal a prediction early only when the information itself is useful for a decision, safety, consent, cost, or latency expectation.

## Adaptive depth

Lookahead depth is not fixed at one or two steps. Two is the normal minimum preparation horizon, not a hard ceiling.

Depth should increase when both **probability** and **linearity** are high. A branch is linear when each next step follows predictably from the prior one with few meaningful forks.

Conceptually:

`depth pressure = probability × linearity × expected user-time saved × preparation leverage / speculative cost`

A very high-probability, highly linear branch may be prepared several steps deep until it reaches a real dependency, safety, permission, preference, destructive, credential, or physical boundary.

Forky, uncertain, expensive, or privacy-sensitive branches remain shallow even when they are plausible.

## Training loop

1. Maintain ranked likely futures.
2. Ask a calibration question only when the expected information gain is worth the interruption.
3. Re-rank branches from the answer.
4. Prepare deeper on high-confidence linear branches.
5. Let natural user intent resolve the branch when possible without exposing predictions first.
6. Give lightweight confidence feedback after resolution when it helps the human estimate likely latency.
7. Score whether the prediction was useful and whether the implied work was actually prepared/executed.
8. Reduce question frequency as the model becomes better calibrated.

The goal is not to predict the user's wording. The goal is to predict enough of the user's **intent and next useful state** that the machine can reduce waiting while remaining non-interfering.
