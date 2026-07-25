# BoxBrain Controller

The controller is a FastAPI service that defines BoxBrain's control-plane
contract. In this alpha it provides health, task queue, policy profile, and
plugin discovery endpoints. It intentionally has no action executor.

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
- GET /api/v1/events`n- GET /api/v1/events/stream (server-sent events with resume support)
- `GET /api/v1/policies`
- `GET /api/v1/plugins`
- `GET /api/v1/targets`
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

The observation policy is loaded from `BOXBRAIN_OBSERVATION_POLICY` (default
`../policies/observation.json`). It enforces frame size limits, child-process
redaction, zero disk retention, and a single concurrent frame capture.

