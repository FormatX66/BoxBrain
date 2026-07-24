# BoxBrain Controller

The controller is a FastAPI service that defines BoxBrain's control-plane
contract. In this alpha it provides health, task queue, policy profile, and
plugin discovery endpoints. It intentionally has no action executor.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m uvicorn boxbrain_controller.main:app --reload
```

## API

- `GET /api/v1/health`
- `GET /api/v1/tasks`
- `POST /api/v1/tasks`
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/policies`
- `GET /api/v1/plugins`

Task submission only records a queued task. No keyboard, mouse, shell, remote
desktop, model, or plugin action is performed.

