# Aurum Operator Completion Contract

This contract defines how work should be driven when Aurum/BoxBrain is being operated on behalf of Bruce.

## Completion rule

A request is not complete when the first command, build, patch, workflow, or diagnostic finishes. It is complete only when the original intended outcome is verified.

Follow the consequence chain automatically:

1. Execute the requested change.
2. Check the result that Bruce would naturally check next.
3. If verification fails, treat that failure as an active blocker, diagnose it, apply a safe fix when the evidence is clear, and rerun verification.
4. Continue through build, smoke test, verification, publication/deployment, and resulting health checks as applicable.
5. Do not report "done" while a required gate is failing, skipped, queued, or unverified.

## Future Branch rule

Use [Future Branch](FUTURE_BRANCH.md) for every meaningful multi-step operation.

Do not wait for the current gate to finish before preparing what is likely to be needed next. Maintain a small ranked set of future branches: the obvious success path, the most likely/high-impact failure paths, the recovery path, and the next-capability path. Prepare the highest-value next one or two steps in advance when doing so is safe and reversible.

A dependency may block execution but should not block preparation. Never cross a real dependency, authorization, safety, or physical boundary early.

Use new evidence to correct assumptions, prune wrong branches, and deepen the branch that actually occurred. Prefer self-capturing diagnostics and prebuilt fallback paths so terse user reports such as "it didn't work" can map immediately to a known stage and prepared response.

## Decision rule

When a branch point does not require human authorization or a personal preference, consult Aurum's own state, desired-state contracts, health evidence, recovery rules, project intent, and prepared Future Branch set first. Prefer the action Aurum's evidence supports rather than bouncing the decision back to Bruce.

Ask Bruce only when the next action genuinely requires information, authorization, physical intervention, an irreversible/risky choice, or a preference Aurum cannot infer safely.

## Recovery and safety rule

Never weaken a safety or verification gate merely to make a build green. Repair the implementation or the test harness, preserve Last Known Good state, and prove the candidate again.

Speculative Future Branch preparation must remain isolated, reversible/disposable, and unable to silently mutate active/LKG state.

## Operator heuristic

Before stopping, ask:

- "What would Bruce check next?"
- "What is he most likely to report if this works?"
- "What is he most likely to report if this fails?"
- "What can safely be prepared now for those outcomes?"

Then perform the safe, reversible, evidence-supported preparation or next step instead of waiting unnecessarily.
