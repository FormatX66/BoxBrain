# BoxBrain Controller

The controller is a FastAPI service that defines BoxBrain's control-plane
contract. In this alpha it provides health, task queue, policy profile, and
plugin discovery, and processing-agent endpoints. It intentionally has no action executor.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
$env:BOXBRAIN_API_TOKEN = '<a-random-value-with-at-least-32-characters>'
python -m uvicorn boxbrain_controller.main:app --reload
```

## API

- `GET /api/v1/health`
- `GET /api/v1/tasks`
- `POST /api/v1/tasks`
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/events`
- `GET /api/v1/events/stream` (server-sent events with resume support)
- `GET /api/v1/policies`
- `GET /api/v1/plugins`
- `GET /api/v1/targets`
- `GET /api/v1/edge-agents`
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
- `POST /api/v1/targets/windows-sandbox/start`
- `GET /api/v1/targets/windows-sandbox/frame`
- `GET /api/v1/safety/emergency-stop`
- `POST /api/v1/safety/emergency-stop/engage`
- `POST /api/v1/safety/emergency-stop/reset`

All API routes except health and documentation require `X-BoxBrain-Token` when
`BOXBRAIN_API_TOKEN` is configured. Tokens shorter than 32 characters are
rejected at startup.

Task submission only records a queued task. No keyboard, mouse, shell, remote
desktop, model, or plugin action is performed. The persistent emergency stop
blocks effectful controller requests such as Sandbox launch; resetting it
requires the exact API confirmation value `RESET`.

Processing-agent intake is a provider-neutral, local-rule planner. It turns
voice, chat, file, or API text into durable projects, searchable memory and
decisions, deduplicated trackable tasks, architecture and engineering plans,
and integration handoffs. It records estimated token use but uses zero provider
tokens and performs no external action. See
[`docs/PROCESSING_AGENTS.md`](../docs/PROCESSING_AGENTS.md).

The optional model endpoint layers one typed OpenAI Agents SDK orchestrator over
that durable local path. It loads `OPENAI_API_KEY` from the process environment
or ignored repository-local `.env.local`, defaults to `gpt-5.6-sol`, records
actual provider token use, deduplicates identical model runs, and exposes no
side-effect tools. Check readiness at `GET /api/v1/agents/runtime`.

Run one safe smoke check with:

```powershell
python -m boxbrain_controller.agent_smoke
```

The observation policy is loaded from `BOXBRAIN_OBSERVATION_POLICY` (default
`../policies/observation.json`). It enforces frame size limits, child-process
redaction, zero disk retention, and a single concurrent frame capture.

## Kali Pi edge agent

The controller reads the Kali Pi agent through a loopback-only SSH tunnel at
`BOXBRAIN_KALI_PI_AGENT_URL` (default `http://127.0.0.1:8787`). It exposes only
a sanitized inventory summary to the dashboard. The controller rejects remote
hosts, embedded URL credentials, extra paths, and non-HTTP schemes for this
setting. See `docs/EDGE_AGENT.md` for setup and upgrade details.
