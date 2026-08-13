# Aurum Integration Notes

**Snapshot:** 2026-08-13

This document translates current self-improving-AI research into a constrained architecture appropriate for BoxBrain/Aurum.

## Recommended architecture

Do **not** begin with unrestricted recursive weight updates. Start with a layered improvement system where the easiest-to-verify changes are promoted first.

```text
                   ┌─────────────────────────┐
                   │  Immutable baseline     │
                   │  + rollback checkpoint  │
                   └────────────┬────────────┘
                                │
                        current accepted agent
                                │
                                ▼
┌───────────┐     ┌──────────────────────────┐
│ task/event│ ──▶ │ trace + outcome recorder │
└───────────┘     └────────────┬─────────────┘
                               ▼
                  ┌─────────────────────────┐
                  │ weakness/novelty miner  │
                  └────────────┬────────────┘
                               ▼
                  ┌─────────────────────────┐
                  │ bounded proposal agent  │
                  │ prompt/skill/code/tool  │
                  └────────────┬────────────┘
                               ▼
                  ┌─────────────────────────┐
                  │ isolated candidate lane │
                  │ branch/container/VM     │
                  └────────────┬────────────┘
                               ▼
                  ┌─────────────────────────┐
                  │ deterministic verifier  │
                  │ tests/benchmarks/rules  │
                  └────────────┬────────────┘
                               ▼
             reject/revert ◀── gate ──▶ promote/archive
```

## Learning ladder

Aurum should move upward only when the lower layer is reliable.

### Level 0 — observation
Record tasks, environment state, tool calls, outputs, errors, latency, resource use, and final outcome.

### Level 1 — persistent memory
Store reusable facts, resolved failures, machine-specific state, successful procedures, and tool metadata. This is learning in the operational sense, but **not** model-weight learning.

### Level 2 — skill extraction
Convert repeated successful traces into deterministic scripts, procedures, tests, or reusable agent skills. This matches the skill-library line of research and reduces future model usage.

### Level 3 — harness evolution
Allow candidate changes to:

- prompts;
- routing policies;
- context-selection rules;
- memory retrieval;
- skill selection;
- tool wrappers;
- retry policies;
- bounded agent source modules.

This is the layer most aligned with DGM, A-Evolve, ShinkaEvolve, SIA, and trace-driven recursive-improve.

### Level 4 — self-generated tests and curricula
When Aurum identifies a weak capability, let it generate test cases or challenge tasks. Keep only challenges with independent verification. AZR and R-Zero are strong references here.

### Level 5 — controlled parameter adaptation
Fine-tune a small local adapter/model only when repeated evidence shows a capability cannot be efficiently captured as memory, code, or skills. SEAL is a major reference for this level.

### Level 6 — improvement-of-improvement
Only after the evaluation layer is robust should candidate systems be permitted to propose changes to the improvement engine itself. Promotion rules and immutable external audit logging should remain outside the candidate's write boundary.

## Best-fit external projects

### ShinkaEvolve
Use as the first experiment for **program evolution with a local evaluator**. It already supports Python, CLI, WebUI, model-provider configuration, local models, and coding-agent workflows.

Potential Aurum use:

```text
Aurum identifies measurable optimization task
→ exports a restricted workspace + evaluator
→ ShinkaEvolve generates candidate variants
→ local BoxBrain worker evaluates each candidate
→ best candidate returned as a patch
→ Aurum promotion gate decides whether to merge
```

### A-Evolve
Use as a reference/wrapper for **agent-level harness evolution**. Its pluggable agent and benchmark interfaces map cleanly onto BoxBrain's existing local-job architecture.

Potential evolvable state:

```text
/Aurum/Evolvable/
    prompts/
    skills/
    routing/
    memory-policies/
    tool-policies/
```

Keep these outside the immutable safety/promotion components.

### recursive-improve
Borrow the simple trace-driven ratchet:

1. capture traces;
2. cluster recurring failures;
3. propose one bounded fix;
4. benchmark old vs candidate;
5. keep or revert;
6. archive evidence.

This is especially attractive for minimizing model usage because deterministic replay, tests, log parsing, Git work, and scoring can run locally.

### AlphaEvolve
Treat as an optional cloud accelerator for tasks that can be represented as code and scored numerically. Avoid making BoxBrain dependent on it; local evolution should remain available.

### Darwin Gödel Machine
Borrow:

- lineage/archive design;
- branching from non-best ancestors;
- empirical validation;
- agent-source self-modification patterns.

Do not copy the research setup's trust assumptions directly into a machine-maintenance agent.

### SEAL / AZR / R-Zero
Keep in the research lane initially. They are most valuable for designing future controlled learning loops where Aurum can genuinely change model behavior rather than only its surrounding software.

## State model for an Aurum learner

Each accepted improvement should be represented as data, not as an opaque mutation:

```json
{
  "improvement_id": "...",
  "parent_id": "...",
  "target": "prompt|skill|tool|routing|code|weights",
  "trigger": "repeated_failure|new_environment|optimization",
  "proposal": "...",
  "baseline_score": 0.0,
  "candidate_score": 0.0,
  "tests": [],
  "resource_delta": {},
  "safety_checks": [],
  "accepted": false,
  "rollback_ref": "git/checkpoint/ref",
  "evidence": []
}
```

## Promotion rules

A candidate should never be promoted merely because an LLM says it is better.

Suggested gate:

```text
all safety tests pass
AND target benchmark improves or stays within tolerance
AND no regression in protected benchmarks
AND resource usage stays within budget
AND change is reproducible
AND rollback checkpoint exists
```

For ambiguous human-preference tasks, keep a human-review gate rather than inventing a numeric reward that can be gamed.

## Evaluation hierarchy

Prefer verification in this order:

1. formal proof / exact checker;
2. executable unit/integration tests;
3. deterministic simulation;
4. objective external measurement;
5. independent model/judge with adversarial checks;
6. self-evaluation by the same candidate model.

The last category should not be used alone for self-promotion.

## Local-first rule

Deterministic work should stay outside model calls:

- file operations;
- dependency checks;
- test execution;
- Git branching/commits/diffs;
- benchmark replay;
- log parsing;
- scoring;
- rollback;
- retry scheduling;
- resource monitoring.

Use model calls primarily for hypothesis generation, code/procedure generation, diagnosis, and synthesis. This keeps the self-improvement loop resumable and limits usage costs.

## Immediate experiment

A safe first Aurum self-learning prototype can be limited to **improving one non-critical local skill**:

```text
1. Pick a deterministic BoxBrain maintenance task.
2. Save baseline traces and benchmark cases.
3. Expose only that skill's directory as evolvable.
4. Generate candidate prompt/script/tool changes.
5. Evaluate in a container with no production credentials.
6. Keep the best candidate only if protected tests pass.
7. Store lineage, scores, and rollback commit.
8. Repeat from the accepted version or a promising ancestor.
```

This provides genuine accumulated self-improvement without granting the learner authority over its own safety controls or production environment.
