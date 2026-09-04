# Development Setup

## Prerequisites

- Git
- Flutter stable with Windows desktop and/or web enabled
- Python 3.11 or newer
- Visual Studio with the Desktop development with C++ workload for Windows
  desktop builds
- Android Studio only if Android support is desired

## Verify Flutter

Open a fresh terminal after changing PATH:

```powershell
where.exe flutter
flutter doctor -v
```

If Flutter is installed but not found, add the SDK's `bin` directory—not the
SDK root—to the user PATH, then reopen Codex, VS Code, and the terminal.

Common SDK locations include:

```text
C:\src\flutter
C:\development\flutter
C:\Users\<you>\development\flutter
```

## Generate platform runners

The repository contains the authored Flutter files but not generated platform
runners. From `ui/`:

```powershell
flutter create --project-name boxbrain_ui --platforms=windows,linux,web .
flutter pub get
flutter analyze
flutter test
```

## Run the controller

From `controller/`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ../Projects/AurumFarmer -e ".[dev]"
python -m pytest
$env:BOXBRAIN_API_TOKEN = '<a-random-value-with-at-least-32-characters>'
python -m uvicorn boxbrain_controller.main:app --reload
```

Tasks and audit events are stored locally in
`controller/data/boxbrain.sqlite3`. This runtime directory is ignored by Git.

## Connect the UI

The repeatable Windows setup uses `https://127.0.0.1:8000`. The manual Flutter
development command still defaults to `http://127.0.0.1:8000`; run it without
asking Flutter to launch a browser:

```powershell
cd ui
flutter run -d web-server --web-port 8080 --dart-define=BOXBRAIN_API_TOKEN=$env:BOXBRAIN_API_TOKEN
```

Override the controller URL at build time without storing it in source:

```powershell
flutter run -d windows --dart-define=BOXBRAIN_API_URL=http://127.0.0.1:8000
```

## Repeatable local startup

The scripts under `installer/` create a Current User-only local certificate,
generate or reuse an ignored local token without printing it, build and serve
the dashboard with the same credential, start the controller on loopback, and
run read-only security checks. See `installer/README.md` for setup, verification,
and exact certificate rollback commands.

The controller launcher changes into `controller/` before startup so relative
plugin and runtime-data paths continue to resolve to the established
`controller/data/boxbrain.sqlite3` database.

## Local API authentication

When `BOXBRAIN_API_TOKEN` is set, every API route except health and the API
documentation requires that token in the `X-BoxBrain-Token` header. Use the
same value as the dashboard build-time `BOXBRAIN_API_TOKEN`. The browser build
contains this development credential, so it is a loopback access control—not a
multi-user secret store. Keep both services bound to localhost.

## Observe Windows Sandbox

The controller uses the enabled `boxbrain.windows-sandbox-observer` manifest for
target status and frames. Each request runs in a separate process with a minimal
environment and returns one correlated protocol-v1 response. Run controller
tests after changing either the manifest, protocol, or plugin entrypoint.

Observation limits live in `policies/observation.json` and can be relocated with
`BOXBRAIN_OBSERVATION_POLICY`. Region coordinates are normalized values from 0
to 1 and are applied as black masks in the child process. Keep retention mode at
`none`; the schema rejects nonzero frame counts or retention ages. Restart the
controller after changing this policy.

Select **Target** and use **Open Windows Sandbox**, or open
`sandbox/BoxBrain-Isolated.wsb` directly. The feed refreshes every two seconds
and remains strictly read-only. The button is enabled by default only when
`BOXBRAIN_ENVIRONMENT=development`; set
`BOXBRAIN_SANDBOX_LAUNCH_ENABLED=false` to disable it explicitly. The configured
profile can be overridden for development with `BOXBRAIN_SANDBOX_PROFILE`, but
no path is accepted from the dashboard API. Do not expose the local controller
port to another host.
## Live audit stream

`GET /api/v1/events/stream` emits append-only audit events as authenticated
server-sent events. Each event uses its SQLite sequence as the SSE ID. Clients
resume with `Last-Event-ID` or `after_sequence`; the dashboard reconnects after
two seconds and retains periodic safety/target reconciliation separately.

## Test the emergency stop

Use the red stop control in the dashboard and confirm **Stop actions**. The
engaged banner remains visible across all screens, and Sandbox launch is blocked
until reset. Click the stopped control, type `RESET`, and select **Reset stop**.
Both transitions appear under **Logs** and survive a controller restart.
