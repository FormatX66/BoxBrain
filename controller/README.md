# BoxBrain Controller

The controller is a FastAPI service that defines BoxBrain's control-plane
contract. In this alpha it provides health, task queue, policy profile, and
plugin discovery, processing-agent endpoints, and a narrow approval-gated Kali Pi
diagnostic executor. It intentionally has no autonomous task executor.

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
- `GET /api/v1/remote-targets`
- `POST /api/v1/remote-targets`
- `DELETE /api/v1/remote-targets/{target_id}`
- `POST /api/v1/remote-targets/{target_id}/probe`
- `POST /api/v1/remote-targets/{target_id}/session`
- `GET /api/v1/remote-targets/{target_id}/diagnostic-proposals`
- `POST /api/v1/remote-targets/{target_id}/diagnostic-proposals`
- `POST /api/v1/diagnostic-proposals/{proposal_id}/execute`
- `GET /api/v1/edge-agents`
- `GET /api/v1/agents`
- `GET /api/v1/agents/runtime`
- `GET /api/v1/agents/diagnostic-runtime`
- `POST /api/v1/processing/runs`
- `POST /api/v1/processing/model-runs`
- `GET /api/v1/processing/model-runs`
- `GET /api/v1/processing/model-runs/{run_id}`
- `GET /api/v1/processing/runs`
- `GET /api/v1/processing/runs/{run_id}`
- `GET /api/v1/processing/usage`
- `GET /api/v1/processing/copilot/runtime`
- `GET /api/v1/processing/copilot/providers`
- `POST /api/v1/processing/copilot/packets`
- `POST /api/v1/processing/copilot/dispatches`
- `GET /api/v1/agent-dashboard`
- `POST /api/v1/chat-organizer/import`
- `GET /api/v1/chat-organizer`
- `GET /api/v1/chat-organizer/chats`
- `GET /api/v1/chat-organizer/imports`
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

Task submission only records a queued task. It performs no keyboard, mouse,
shell, model, or plugin action. Remote-target routes separately manage
operator-authorized private host profiles, probe a fixed host/port, and launch a
known operating-system SSH, WinRM, RDP, or lab-only Telnet client with a fixed
argument list after exact confirmation. They accept no command text and store no
passwords. The persistent emergency stop blocks session and Sandbox launch;
resetting it requires the exact API confirmation value `RESET`.

The built-in Kali Pi alone supports model-proposed diagnostics. The model returns
one typed action from a four-item allowlist and has no execution tool. A separate
endpoint accepts only `RUN`, rechecks private scope and the emergency stop, then
runs the action's fixed SSH command with a deadline and output cap. Prompt text is
never used as command input, diagnostic output is returned to the operator but not
written to the audit log, and general remote targets remain human-operated.

Processing-agent intake is a provider-neutral, local-rule planner. It turns
voice, chat, file, or API text into durable projects, searchable memory and
decisions, deduplicated trackable tasks, architecture and engineering plans,
and integration handoffs. It records estimated token use but uses zero provider
tokens and performs no external action. See
[`docs/PROCESSING_AGENTS.md`](../docs/PROCESSING_AGENTS.md).

Script-first routing, its versioned local registry, duplicate protection, and
usage-reduction metrics are documented in
[`docs/SCRIPT_FIRST_ROUTING.md`](../docs/SCRIPT_FIRST_ROUTING.md).

The BB-007 GitHub Copilot CLI worker creates bounded review packets for local
Windows file organization, code, and plugin tasks. Microsoft Copilot for
Windows is reported separately as a manual-only app. Automated sending requires
the exact `SEND TO GITHUB COPILOT` confirmation; the GitHub CLI is restricted to
plan mode and one packet read, and returned work is never applied automatically. See
[`docs/COPILOT_WINDOWS_OFFLOAD.md`](../docs/COPILOT_WINDOWS_OFFLOAD.md).

The ChatGPT organizer accepts an authenticated, normalized metadata snapshot,
preserves existing project membership, classifies loose chats with inspectable
local rules, and records deduplicated sync history. It has no ChatGPT mutation
or browser-storage capability. See
[`docs/CHATGPT_ORGANIZER.md`](../docs/CHATGPT_ORGANIZER.md).

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
