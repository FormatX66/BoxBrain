# Script-First Task Routing

BoxBrain classifies work before any model execution so routine work does not
consume GPT context on every step. The controller exposes the router under
`/api/v1/processing` and stores append-only operational metrics in
`data/script-first-events.jsonl` (or `BOXBRAIN_DATA_DIR`).

## Routes

| Route | Use when | Fallback |
| --- | --- | --- |
| Script | A registered, versioned procedure covers deterministic, repetitive, or data-heavy work | Hybrid, then GPT on a bounded exception |
| GPT | The task is ambiguous, diagnostic, novel, or requires adaptive reasoning | Hybrid when local evidence collection helps |
| Hybrid | Local preprocessing is useful but reasoning, code repair, or human approval is still required | GPT for reasoning; human review for impact |

The decision includes a confidence value, reasons, registered-script status,
queue state, fallback route, and an optional future `model_lane`. High-impact or
destructive work is always Hybrid and requires human review. The current
registry contains no write-capable scripts.

## Initial script registry

- `text.summary@1.0.0`: counts and bounded excerpts for large text.
- `jsonl.summary@1.0.0`: JSONL validation, key frequencies, and bounded errors.
- `text.diff@1.0.0`: bounded unified diff and change counts.
- `files.inventory@1.0.0`: hashes a bounded repository-relative file set.

Each registry entry declares its input/output contract, permissions, impact,
idempotency, and rollback strategy. Scripts return structured JSON suitable for
compact model review. They cannot execute a shell, call a model, or read outside
the configured repository root.

## Duplicate prevention

Every run requires an idempotency key. A successful key is not executed twice.
When a `BB-###` task is already present in `.codex/queue/COMPLETE.md`, execution
also returns `duplicate` so verified work is not repeated. Active queue entries
are reported to the caller for checkpoint-aware orchestration.

## Escalation and safety

Expected input, JSON, file, and boundary errors are reduced to a bounded error
type/message and returned as `escalated` with GPT as the fallback. No model call
is made automatically. Unknown scripts also escalate instead of being treated
as arbitrary commands.

Future write-capable scripts must declare a rollback method and are rejected
without the exact `APPROVE HIGH IMPACT` confirmation. Destructive procedures
must remain Hybrid with a separate operator gate; they must never be added as a
silent script-first path.

## Metrics

`GET /api/v1/processing/script-metrics` reports route counts, script runs,
successful local runs, avoided model calls, prevented duplicates, escalations,
average duration, reliability, and error rate. These values are observational;
the router does not invent token savings when provider usage is unavailable.

## API examples

Classify before model execution:

```json
POST /api/v1/processing/route
{
  "task_id": "BB-006",
  "description": "Summarize the nightly JSONL log",
  "script_id": "jsonl.summary",
  "deterministic": true,
  "repetitive": true,
  "data_heavy": true
}
```

Run the selected local procedure:

```json
POST /api/v1/processing/script-runs
{
  "task_id": "BB-006",
  "script_id": "jsonl.summary",
  "payload": {"text": "{\"status\":\"ok\"}"},
  "idempotency_key": "BB-006-nightly-log-2026-08-08"
}
```

If the result is `escalated`, pass only its compact `data` evidence plus the
original objective into the chosen model lane.

## Copilot worker lane

BB-007 adds a separate approval-gated Copilot lane for local Windows
file-organization planning, Windows code, and plugin code. It does not weaken
the Script/GPT/Hybrid decision: local scripts still handle deterministic work,
while Copilot receives only a minimal prepared packet after operator review.
Copilot output is a proposal and is never applied by the offload service. See
[`COPILOT_WINDOWS_OFFLOAD.md`](COPILOT_WINDOWS_OFFLOAD.md).
