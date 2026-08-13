# Public Interface Matrix

**Verified:** 2026-08-13

This file distinguishes a **hosted/public service interface** from **open-source code that must be run locally**.

| System | Hosted API | Python/library API | CLI | Web UI | Public code | Public models/weights | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| **AlphaEvolve** | ✅ Google Cloud `v1alpha` API | ✅ Cloud client/sample code | ✅ `ae` CLI | Cloud/Gemini Enterprise UI path | ✅ samples/tools | N/A as standalone weights | Most directly callable managed self-evolution service found. Requires Google Cloud project, billing, Gemini Enterprise/Discovery Engine access. |
| **ShinkaEvolve** | Via configured LLM providers | ✅ `shinka` / `ShinkaEvolveRunner` | ✅ `shinka_launch`, inspection tools | ✅ `shinka_visualize` | ✅ | Uses configured local/remote models | Strong local integration option. Supports local models, provider APIs, and headless Codex/Claude mutation backends. |
| **A-Evolve** | No dedicated hosted service required | ✅ `agent_evolve` | Via package/scripts | Not the primary interface | ✅ | Bring your own model | Framework interface is intentionally pluggable: agent, benchmark/evaluator, and evolution engine. Good fit for wrapping Aurum itself. |
| **recursive-improve** | No | ✅ tracing package | ✅ init/benchmark/ratchet tooling | ✅ local dashboard | ✅ | Bring your own model | Captures OpenAI/Anthropic/LiteLLM traces, lets a coding agent analyze failures, applies changes, benchmarks, then keeps/reverts. |
| **Darwin Gödel Machine** | No | Source-level Python components | ✅ run via `python DGM_outer.py` | No official hosted UI found | ✅ Apache-2.0 | Foundation models supplied externally | Research implementation. Requires Docker and model API keys. Directly executes model-generated code, so sandboxing is mandatory. |
| **SEAL (Self-Adapting Language Models)** | No | Research Python code | Experiment scripts | No official hosted UI found | ✅ MIT | Base models supplied by user | Actual weight adaptation from model-generated self-edits. Research setup is GPU-heavy; README reports experiments using 2× A100/H100 GPUs. |
| **Absolute Zero Reasoner (AZR)** | No hosted service found | Training/eval code | Shell/Python experiment scripts | No | ✅ MIT | ✅ released model(s) referenced by project | Self-generated code/math curriculum with verifiable execution rewards. Better viewed as a training system than an agent API. |
| **R-Zero** | No hosted service found | Training framework | ✅ single-script experiment path | No | ✅ | Base/checkpoint models via Hugging Face | Challenger/Solver co-evolution. Uses Hugging Face, Weights & Biases, and OpenAI evaluation credentials in published setup. |
| **SIA** | No hosted service found | ✅ local framework | Local run path | Not primary | ✅ | Depends on target | 2026 framework designed to update both agent harness and task-specific model weights based on benchmark feedback. |
| **Dr. Zero** | No hosted service found | Research framework | Local training scripts | No | ✅ Meta/Facebook Research repo | Base models supplied by user | Search-agent self-evolution without initial training data. |
| **SAGE** | No hosted service found | Research code | Local training/eval path | No | ✅ Amazon Science repo | Base models supplied by user | RL-based skill-library learning; useful reference for durable skill acquisition. |

## Interfaces that are immediately usable by Aurum

### 1. AlphaEvolve — managed remote evolution service

As of July 2026 Google documents a production-oriented AlphaEvolve Cloud API under Gemini Enterprise / Discovery Engine. It exposes experiment lifecycle operations and program acquisition/evaluation workflows. This makes it usable as a remote evolutionary optimizer rather than only as a paper.

Useful interface pattern:

```text
Aurum evaluator / local sandbox
        ↕
AlphaEvolve Cloud API
        ↕
program candidates + experiment state
```

Important: AlphaEvolve is strongest when the target has an objective automated evaluator. The cloud generates candidates; evaluation can be run locally and scores submitted back.

### 2. ShinkaEvolve — best current local evolutionary toolkit candidate

Current public interfaces include:

```bash
pip install shinka-evolve
shinka_launch variant=circle_packing_example
shinka_visualize --port 8888 --open
```

It also exposes a Python runner and coding-agent skills. By 2026 it supports headless subscription-backed mutation models such as Codex/Claude as well as configurable API/local models. That makes it particularly relevant to BoxBrain's local-first architecture.

### 3. A-Evolve — best generic "evolve my existing agent" abstraction

Minimal published interface:

```python
import agent_evolve as ae

evolver = ae.Evolver(
    agent="./my_agent",
    benchmark="swe-verified",
)
results = evolver.run(cycles=10)
```

The important design feature is not the benchmark itself; it is the adapter boundary. A custom agent implements `solve()`, while a custom benchmark/evaluator supplies tasks and scores. Aurum could therefore expose a restricted evolvable workspace rather than giving an optimizer unrestricted access to the full BoxBrain system.

### 4. recursive-improve — practical trace-driven ratchet

This is a smaller open-source implementation, but its workflow is directly useful:

```text
run agent
→ save traces
→ identify repeated failures
→ coding agent proposes targeted fixes
→ run benchmark
→ keep or revert
→ repeat
```

It also provides a local dashboard and an autonomous `/ratchet` loop. This is conceptually close to BoxBrain's local-first queued-job approach because deterministic evaluation can remain local while model calls are reserved for bounded proposal steps.

## Research systems that are open but not plug-and-play services

### Darwin Gödel Machine

Public Apache-2.0 Python source; run locally. Requires Docker and external model credentials. It is valuable as a reference implementation of open-ended scaffold evolution, but its published code is benchmark/research oriented rather than a stable general-purpose service API.

### SEAL

Public MIT code. This is one of the clearest examples of persistent **weight** adaptation rather than memory-only adaptation. It is therefore strategically important, but much heavier to integrate than scaffold evolution.

### AZR and R-Zero

Both publish training code for self-generated curricula. Their public interface is primarily a training pipeline, not an end-user agent endpoint. Their most reusable idea for Aurum is the **self-generated challenge → verified outcome → retained learning** loop.

## Recommended access priority for BoxBrain/Aurum

1. **ShinkaEvolve** — local integration experiment.
2. **A-Evolve** — evaluate as a generic evolvable-agent wrapper.
3. **recursive-improve** — borrow trace/benchmark/keep-or-revert mechanics.
4. **AlphaEvolve API** — optional remote accelerator for measurable code/algorithm problems.
5. **DGM** — mine architecture and safety patterns; do not give unrestricted host access.
6. **SEAL / AZR / R-Zero** — research lane for eventual controlled weight adaptation and self-generated curricula.

## Safety boundary for all public interfaces

Self-improvement systems frequently execute generated code. Use:

- disposable containers/VMs;
- no inherited production credentials;
- read-only source snapshots by default;
- strict CPU/RAM/time/network budgets;
- external deterministic tests;
- a candidate branch/worktree, never the production branch;
- explicit promotion gates;
- immutable baseline checkpoints and automatic rollback;
- logging that the candidate process cannot rewrite.

A self-improver should be allowed to propose changes to itself before it is allowed to change the mechanism that decides whether those changes are good.
