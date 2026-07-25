# BoxBrain

BoxBrain is a modular controller for connecting cloud AI planning to an
isolated computer lab. The first milestone is deliberately small: a Flutter
mission-control UI, a Python/FastAPI controller API, a plugin boundary, policy
profiles, and an audit-friendly task queue.

This repository is an initial alpha skeleton. It does **not** yet execute
keyboard, mouse, remote-desktop, shell, or model actions.

## Repository layout

```text
BoxBrain/
├── ui/             Flutter dashboard source
├── controller/     FastAPI controller service
├── plugins/        Plugin contract and an inert example plugin
├── docs/           Product, architecture, security, and setup notes
├── installer/      Local prerequisite checks and future image notes
└── tests/          Cross-component test notes
```

## Quick start

### Recommended Windows HTTPS setup

From the repository root, create a BoxBrain-only development certificate,
generate the local API token, and build the dashboard:

```powershell
.\installer\setup-local-tls.ps1
.\installer\initialize-local-auth.ps1
.\installer\build-dashboard.ps1
```

Start these in separate terminals:

```powershell
.\installer\start-controller.ps1
.\installer\serve-dashboard.ps1
```

Open `https://127.0.0.1:8080/` for BoxBrain and
`https://127.0.0.1:8000/docs` for the API explorer. The certificate is trusted
only for the current Windows user. See `installer/README.md` for verification
and exact rollback commands.

### Manual cross-platform setup

Set the same local token in the controller and dashboard terminals. Use a unique
random value with at least 32 characters and never commit it:

```powershell
$env:BOXBRAIN_API_TOKEN = '<your-random-local-token>'
```

### 1. Flutter dashboard

Flutter must be available on `PATH`. From `ui/`, generate the missing platform
runners once, then run the app:

```powershell
flutter create --project-name boxbrain_ui --platforms=windows,linux,web .
flutter pub get
flutter run -d windows
```

For the browser dashboard, use the web server device so Flutter does not need
to launch Chrome itself:

```powershell
flutter run -d web-server --web-port 8080 --dart-define=BOXBRAIN_API_TOKEN=$env:BOXBRAIN_API_TOKEN
```

The source is already present under `ui/lib`; `flutter create` is only needed
to add Flutter's generated Windows, Linux, and web runner files.

### 2. Controller API

From `controller/`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
$env:BOXBRAIN_API_TOKEN = '<the-same-local-token>'
python -m uvicorn boxbrain_controller.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the manual HTTP API explorer.

### 3. Read-only Windows Sandbox target

On Windows, select **Target** and use **Open Windows Sandbox**, or open
`sandbox/BoxBrain-Isolated.wsb` directly. Its profile disables networking,
clipboard, audio/video input, printer redirection, and vGPU. The controller
discovers that window and exposes a view-only frame in the dashboard.

The development launcher accepts no path from the dashboard and can open only
the checked-in `.wsb` profile. Every request is added to the append-only audit
log. Status and frames run through the separate
`boxbrain.windows-sandbox-observer` process with only describe/frame
capabilities, strict identity correlation, timeouts, size limits, and PNG digest
verification. The observer has no keyboard, mouse, clipboard, file, arbitrary
process, or shell API. Frames are fetched as authenticated bytes rather than
exposed as unauthenticated image URLs. The checked-in observation policy caps
frames at 1280 pixels and 8 MiB, applies configured black masks inside the child
process, and retains zero frames on disk. Only one capture may run at a time.
Keep the controller bound to `127.0.0.1`; the frame endpoint is intended only
for this local dashboard.

### 4. Queue and audit tasks

Use **Tasks** to queue a goal for the connected Sandbox. Tasks are stored in
`controller/data/boxbrain.sqlite3`, survive controller restarts, and create an
append-only event visible under **Logs**. New events arrive over an authenticated
server-sent event stream with sequence-based resume and automatic reconnect.
Queueing records intent only; the executor remains disabled.

### 5. Emergency stop

Use the red stop control from any dashboard screen to block Sandbox launches
and future executor actions. The state survives controller restarts and every
engage/reset request is audited. Read-only observation remains available while
stopped. Resetting requires typing `RESET` in the confirmation dialog.

### 6. Verify

```powershell
cd controller
python -m pytest

cd ..\ui
flutter analyze
flutter test
```

The scripts in [installer/README.md](installer/README.md) can create and remove
the Current User development certificate, generate the local token, build and
serve the authenticated dashboard, start the loopback controller, and run a
read-only security check without printing the credential.

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for setup details and
[docs/SECURITY.md](docs/SECURITY.md) before adding any executor.
