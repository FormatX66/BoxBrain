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

## Model-backed orchestrator

`POST /api/v1/processing/model-runs` runs the deterministic crew first, then
gives its classification, safety state, and selected prior local memory to one
typed OpenAI Agents SDK orchestrator. The model returns a summary, decisions,
tasks, specialist handoffs, research queries, architecture notes,
implementation steps, integration requests, and risk flags.

The deterministic project classification remains authoritative. Model runs are
immutable, linked to their local run, and unique by local run plus model, so a
repeat request does not spend provider tokens again. The runtime defaults to
`gpt-5.6-sol` and can be configured with:

- `BOXBRAIN_AGENT_RUNTIME_ENABLED`
- `BOXBRAIN_AGENT_MODEL`
- `BOXBRAIN_AGENT_MAX_OUTPUT_TOKENS`
- `OPENAI_API_KEY`

No provider call occurs on `POST /api/v1/processing/runs`.

## Dashboard workspace

The authenticated dashboard now includes an **Agents** destination. It loads the
runtime status, all ten crew definitions, durable workspace totals, and recent
agent tasks directly from the controller.

The intake composer defaults to **Local** mode, so voice notes can be processed
without provider billing. **Use model reasoning** is an explicit opt-in. Model
errors remain visible and the operator can switch back to the local crew without
losing the durable local run. Each durable agent task has an action menu for
marking it done, dismissing it, or reopening it; the workspace totals refresh
after a successful update.

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

`token_budget` is an estimated local planning allowance and also bounds how much
intake text is sent to the model endpoint. The deterministic endpoint always
uses zero provider tokens. Model runs record the Agents SDK's actual request,
input, output, and total token counts; aggregate provider use appears in the
usage summary and dashboard. The model output cap is separately controlled by
`BOXBRAIN_AGENT_MAX_OUTPUT_TOKENS`.

## Safety boundary

- Processing is advisory and planner-only.
- The deterministic endpoint calls no model provider, web search, connector,
  shell, device, keyboard, or pointer action.
- The model endpoint calls only the configured model provider and exposes no
  connector, shell, device, keyboard, pointer, deployment, or deletion tools.
- Effectful language is surfaced as `needs_approval` unless the request records
  external access as allowed.
- Even when external access is allowed, the Integration Agent only creates a
  handoff artifact; the eventual connector or executor remains separately gated.
- Runs and usage events are append-only in SQLite.
- Normal BoxBrain API-token, trusted-host, CORS, and no-store protections cover
  all processing endpoints.

## API

- `GET /api/v1/agents`
- `GET /api/v1/agents/runtime`
- `POST /api/v1/processing/runs`
- `POST /api/v1/processing/model-runs`
- `GET /api/v1/processing/model-runs`
- `GET /api/v1/processing/model-runs/{run_id}`
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
