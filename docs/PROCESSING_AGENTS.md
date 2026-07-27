# Processing agents

BoxBrain's processing crew is the provider-neutral planner layer between messy
human intake and the existing controller task, policy, plugin, and audit
boundaries. It accepts voice, chat, API, or file text and produces structured,
reviewable artifacts. It does not execute target actions or connector changes.

## Crew

| Agent | Character | Main responsibility |
| --- | --- | --- |
| Orchestrator | The Conductor | Normalize imperfect intake and route the run. |
| Usage Controller | The Quartermaster | Estimate token use, enforce the budget, and defer optional agents. |
| Security Agent | The Sentinel | Detect effectful intent and require approval. |
| Project Librarian | The Librarian | Classify the material into a project. |
| Knowledge Manager | The Archivist | Create durable summaries and decision notes. |
| Search and Memory Agent | The Scout | Prepare focused retrieval and research handoffs. |
| Task Manager | The Dispatcher | Extract proposed actions and dependencies. |
| Architecture Agent | The Architect | Prepare data-flow, contract, and boundary work. |
| Engineering Agent | The Engineer | Prepare implementation and verification work. |
| Integration Agent | The Bridge | Route approved connector handoffs without changing external state. |

The first six agents form the core path. Scout, Architect, Engineer, and Bridge
are selected from the request's intent. Unrecognized or fragmented input still
falls back to the core path rather than failing strict parsing.

## Processing flow

1. The Conductor collapses whitespace and immediate transcript repetitions.
2. The Quartermaster estimates the input and per-agent allowance.
3. The Sentinel records security posture and approval requirements.
4. The Librarian chooses an explicit project hint or a known project alias.
5. The Archivist and Dispatcher create memory and task artifacts.
6. Intent-specific agents add research, architecture, implementation, or
   integration handoffs.
7. One SQLite transaction saves the run, usage ledger, project activity,
   memories, decisions, and deduplicated tasks.

A request fingerprint includes normalized content, source, project hint, budget,
and external-access setting. Repeating the same request returns the existing run
instead of spending the budget twice.

## Operational workspace

Successful runs now produce durable local state:

- projects with activity, memory, and open-task counts;
- immutable summary and decision records linked to their source run;
- deduplicated tasks with `open`, `done`, and `dismissed` states;
- append-only task status history;
- project-filtered memory listing and keyword search;
- a compact dashboard showing project, memory, run, usage, and task totals.

The Scout searches this workspace before preparing an external research handoff,
so prior BoxBrain memory is used first. The Librarian, Archivist, and Dispatcher
materialize these records automatically when a run is first saved.

## Budget semantics

`token_budget` is an estimated planning allowance. The current implementation
uses local deterministic rules, so `provider_tokens_used` is always zero. When a
budget is too small, the Quartermaster marks later agents `deferred` and returns
a partial result; the controller does not crash or silently exceed the limit.

## Safety boundary

- Processing is advisory and planner-only.
- No model provider, web search, connector, shell, device, keyboard, or pointer
  action is called by this runtime.
- Effectful language is surfaced as `needs_approval` unless the request records
  external access as allowed.
- Even when external access is allowed, the Integration Agent only creates a
  handoff artifact; the eventual connector or executor remains separately gated.
- Runs and usage events are append-only in SQLite.
- Normal BoxBrain API-token, trusted-host, CORS, and no-store protections cover
  all processing endpoints.

## API

- `GET /api/v1/agents`
- `POST /api/v1/processing/runs`
- `GET /api/v1/processing/runs`
- `GET /api/v1/processing/runs/{run_id}`
- `GET /api/v1/processing/usage`
- `GET /api/v1/agent-dashboard`
- `GET /api/v1/projects`
- `GET /api/v1/memory`
- `GET /api/v1/memory/search`
- `GET /api/v1/agent-tasks`
- `POST /api/v1/agent-tasks/{task_id}/status`

Example intake:

```json
{
  "content": "Build out out the main processing agents for Box Brain.",
  "source": "voice",
  "token_budget": 2000,
  "external_access_allowed": false
}
```

The response contains normalized input, project and intent classification,
per-agent steps, structured artifacts, approval state, and the usage budget.
