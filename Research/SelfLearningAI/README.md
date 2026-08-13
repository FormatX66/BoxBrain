# Self-Learning / Self-Building AI Reference

**Snapshot date:** 2026-08-13  
**Purpose:** Living technical reference for BoxBrain / Aurum research into AI systems that can improve their own behavior, scaffolding, code, skills, curricula, or model weights.

## What counts as self-learning here?

The term is overloaded. This reference separates systems by **what persists after the learning loop**:

1. **Output self-refinement** — improves an answer during one run; no persistent learning.
2. **Memory / skill accumulation** — stores reusable knowledge, traces, skills, prompts, or procedures outside the model weights.
3. **Scaffold / harness self-improvement** — modifies prompts, tools, workflows, memory policies, code, or agent architecture.
4. **Program evolution / self-building** — generates and evaluates new code/program variants over repeated generations.
5. **Weight adaptation** — updates neural-network parameters based on new experience or self-generated data.
6. **Curriculum self-generation** — generates its own increasingly difficult training tasks and learns from them.
7. **Recursive self-improvement (RSI)** — the improvement mechanism itself can be changed or improved. Current systems remain bounded; unrestricted general RSI is not a solved capability.

## Current high-signal systems

| System | Main self-improvement target | Public access | Practical relevance |
|---|---|---|---|
| Darwin Gödel Machine (DGM) | Agent source code / scaffold | Open-source local code | Very high for self-modifying agents |
| ShinkaEvolve | Programs / scientific code | Python package, CLI, WebUI, agent skills | Very high for local evolutionary loops |
| AlphaEvolve | Algorithms / codebases | Google Cloud API + CLI + examples | Very high where a verifier/metric exists |
| A-Evolve | Agent prompts, skills, memory, tools, harness | PyPI + Python API + open source | Very high for evolving an existing agent |
| recursive-improve | Agent code using execution traces | Python/CLI + dashboard + coding-agent skill | High for practical local ratcheting |
| SIA | Harness + model weights | Open-source local framework | High research value; hybrid scaffold/weight loop |
| SEAL | Model weights via model-generated self-edits | Open-source research code | High for persistent model adaptation |
| Absolute Zero Reasoner (AZR) | Reasoning weights + self-generated curriculum | Code + models + logs | High for zero-data self-play research |
| R-Zero | Challenger + solver reasoning models | Open-source training framework | High for co-evolving curriculum research |
| Dr. Zero | Search agent + self-generated tasks | Open-source code | High for self-evolving search agents |
| SAGE | Skill library + RL policy | Open-source code | High for persistent skill acquisition |

## Important boundary

A model with a memory database is not automatically a self-learning model. A coding agent that edits a project is not automatically self-improving. This repository uses **persistent capability gain** plus an **evaluation/selection loop** as the practical threshold for calling a system self-improving.

## Strongest design pattern seen across current work

```text
experience / task stream
        ↓
trace + state capture
        ↓
weakness / novelty detection
        ↓
proposal generation
        ↓
candidate change
(code / skill / prompt / weights / curriculum)
        ↓
external verifier / benchmark / reward
        ↓
accept, reject, branch, or revert
        ↓
persistent archive + next generation
```

The verifier is critical. The strongest published systems rely on executable tests, formal constraints, benchmark scores, or other external reward signals rather than trusting the model's own opinion of whether it improved.

## Files

- [`PUBLIC_INTERFACES.md`](PUBLIC_INTERFACES.md) — which systems can actually be called, embedded, installed, or operated today.
- [`AURUM_INTEGRATION.md`](AURUM_INTEGRATION.md) — architecture lessons and practical integration path for BoxBrain/Aurum.
- [`SOURCES.md`](SOURCES.md) — primary papers, official project pages, repositories, and rolling survey sources.

## Maintenance rule

Treat this as a dated snapshot. Public interfaces, model availability, licenses, cloud access, and project status can change quickly. Re-verify primary sources before integrating a dependency.
