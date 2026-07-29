# BoxBrain Memory Priority Stack

A repository-first memory and problem-solving layer for BoxBrain.

## Core rule

When a previous approach has been demonstrated to work, use it first. Only deviate when a verified blocker exists. If blocked, pivot once to the nearest proven alternative and continue execution.

## Priority order

| Score | Rule |
|---:|---|
| 100 | Proven workflow first |
| 95 | Repository and existing artifacts first |
| 90 | Execute before explaining |
| 85 | Descend the artifact ladder |
| 80 | Pivot once after a verified blocker |
| 75 | Use available tools and integrations |
| 70 | Explain after delivery |
| 65 | Capture successful improvements as reusable memory |

## Artifact ladder

1. Finished product
2. Render-ready project
3. Editor-ready assets
4. Frame pack / source assets
5. Executable code
6. Documentation / handoff

The system must not stop at “I can’t” while a lower artifact level remains possible.

## Quick start

```bash
python -m boxbrain_memory.cli choose memory/example_context.json
python -m unittest discover -s tests
```

## Integration target

Have the orchestrator load:

- `memory/priority_stack.json`
- `memory/proven_workflows.json`
- `memory/failure_patterns.json`

The resolver in `src/boxbrain_memory/resolver.py` ranks candidate actions using these files.
