# BoxBrain Cue Hold

This file stores ideas, future implementations, experiments, and partially formed specifications that are intentionally **not ready to build**.

## Rules

- `run queue` MUST NOT execute items from this file.
- Hold items may be read for context and duplicate detection only.
- Each hold item should have a stable ID, preferably `BH-###` for BoxBrain Hold.
- Hold items may include notes, open questions, dependencies, references, and proposed acceptance criteria.
- A hold item becomes active only when the user or an authorized project workflow explicitly promotes it to the active queue.
- Promotion should preserve the original hold ID in the new task record for traceability and assign a normal active `BB-###` task ID.
- Do not silently promote an idea because it seems easy or useful.
- Hold items should synchronize between Git and local Desktop copies just like the active queue, but they are never considered runnable work.

## Suggested Format

```text
[HOLD BH-001]
STATUS: HOLD
TITLE: Example future feature

WHY ON HOLD:
Needs more design work.

NOTES:
Preserve the idea here without scheduling implementation.

PROMOTION CRITERIA:
- Architecture decided
- Dependencies identified
- User explicitly promotes to queue

END HOLD
```

## Held Ideas

[HOLD BH-001]
STATUS: HOLD
TITLE: Multi-GPT Revolving Cycle

WHY ON HOLD:
The concept needs architecture, account/usage-limit handling, model-routing rules, and implementation details before it is ready to build.

NOTES:
Design a revolving multi-ChatGPT workflow that can distribute work across multiple available ChatGPT sessions/accounts or execution lanes instead of allowing a single exhausted usage window to stop the larger workflow. The orchestration layer should know which lane is available, which usage/cap type is exhausted, and when each lane is expected to become usable again. Work should move to another eligible lane when appropriate while preserving task state and context.

The concept should integrate with the Codex Cue system. If a task cannot run because the currently selected GPT/session has reached the relevant usage cap, determine whether another authorized lane can perform the task. If so, hand the task off without duplicating completed work. If no lane is currently eligible, keep the task queued and associate it with the appropriate future rolling-cycle availability rather than repeatedly consuming attempts.

Future design should consider:
- Multiple authorized ChatGPT sessions/accounts or model lanes.
- Per-lane usage/cap awareness and reset-cycle tracking.
- Automatic routing to an eligible lane based on task requirements and remaining capability.
- Preservation of task state, context, artifacts, logs, and completion checks during handoff.
- Duplicate-work prevention by checking Cue Complete and current task state before execution.
- Local/Git queue continuity when cloud/model access is unavailable.
- Safe authentication and strict separation of credentials between accounts/machines.
- A scheduler/orchestrator that revisits held or blocked tasks when the applicable rolling cycle becomes available.
- Clear audit logs showing which lane handled each task and why routing changed.
- Rules for tasks that require a specific model/capability and therefore cannot simply move to another lane.

PROMOTION CRITERIA:
- Define the exact meaning of a GPT/session/account "lane."
- Determine what usage/reset information can be observed reliably and legally.
- Define routing, retry, and anti-duplication rules.
- Define secure credential/session handling.
- Define integration with Codex Cue, Cue Hold, and Cue Complete.
- User explicitly promotes the concept to the active queue.

END HOLD

[HOLD BH-002]
STATUS: HOLD
TITLE: Script-First Task Offload / GPT Usage Reduction

WHY ON HOLD:
The concept needs a task-classification model, execution boundaries, safety rules, and measurement criteria before it is ready to build.

NOTES:
Design BoxBrain/Codex so repetitive, deterministic, data-heavy, or machine-execution work is preferentially handled by local scripts and conventional automation instead of consuming GPT reasoning/context on every step. GPT should be reserved for work where language understanding, ambiguous judgment, planning, code generation, diagnosis, or adaptive reasoning provides meaningful value.

The goal is to reduce GPT usage and token/context load while improving reliability, repeatability, speed, and recoverability of long service-model and computer-scripting workflows. GPT can design, generate, repair, or select scripts, but once a procedure is stable, the routine execution should generally move to a script or service rather than repeatedly asking GPT to perform the same mechanical work.

Future design should classify tasks approximately as follows:
- SCRIPT-FIRST: file copying/syncing, directory scans, checksums, parsing structured logs, deterministic transforms, backups, scheduled jobs, health checks, polling, API calls with fixed schemas, queue bookkeeping, duplicate checks, retry logic, process/service control, inventory collection, known deployment sequences, and repeatable calculations.
- GPT-FIRST: ambiguous troubleshooting, architecture/design, interpreting novel failures, requirements discovery, natural-language synthesis, deciding among uncertain alternatives, generating new code, reviewing complex changes, and other tasks requiring contextual judgment.
- HYBRID: GPT creates or selects an execution plan/script; scripts perform bulk/repetitive work; GPT receives compact structured results and only intervenes on exceptions or decision points.

The task router should estimate whether GPT involvement is actually required before sending a job to a model. Large raw inputs should be preprocessed locally when practical so GPT receives summaries, diffs, error excerpts, metadata, or other compact structured context rather than entire repetitive datasets.

The concept should integrate with the Multi-GPT Revolving Cycle (BH-001) and Codex Cue system. Script-capable work should be offloaded before attempting to consume another GPT lane. GPT lane rotation should therefore be a fallback for genuine model work, not a substitute for deterministic local automation.

Future design should consider:
- A Script vs GPT vs Hybrid task classifier.
- Token/usage-cost estimation before model execution when measurable.
- Local preprocessing and context compression.
- Reusable script library with versioning, tests, documentation, and known input/output contracts.
- Structured machine-readable script output so GPT only receives relevant results.
- Exception-driven escalation: scripts handle normal paths; GPT handles failures or ambiguity.
- Idempotency and duplicate-work prevention using Cue and Cue Complete state.
- Logging of whether each task was handled by script, GPT, or hybrid and why.
- Human-review gates for high-impact or destructive actions.
- Security boundaries so generated scripts cannot silently exceed their authorized scope.
- Metrics comparing GPT usage, execution time, reliability, and error rate before/after offload.
- Ability to promote frequently repeated GPT procedures into tested scripts after they stabilize.

PROMOTION CRITERIA:
- Define Script/GPT/Hybrid classification rules and confidence thresholds.
- Identify the highest-volume current BoxBrain/Codex tasks suitable for script offload.
- Define script sandboxing, permissions, logging, rollback, and human-review requirements.
- Define the interface between Cue, the task router, script runner, and GPT/model lanes.
- Define how token/usage savings and task reliability will be measured.
- Establish a reusable script registry/library format.
- User explicitly promotes the concept to the active queue.

END HOLD

## Promotion Flow

`Cue Hold` -> explicit promote command -> active `Codex Cue` task -> build/test/verify -> `Cue Complete`

The repository/system remains the final source of truth for implementation state.
