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
python -m pip install -e ".[dev]"
python -m pytest
python -m uvicorn boxbrain_controller.main:app --reload
```

Tasks and audit events are stored locally in
`controller/data/boxbrain.sqlite3`. This runtime directory is ignored by Git.

## Connect the UI

The default controller URL is `http://127.0.0.1:8000`. Run the web dashboard
without asking Flutter to launch a browser:

```powershell
cd ui
flutter run -d web-server --web-port 8080
```

Override the controller URL at build time without storing it in source:

```powershell
flutter run -d windows --dart-define=BOXBRAIN_API_URL=http://127.0.0.1:8000
```

## Observe Windows Sandbox

Select **Target** and use **Open Windows Sandbox**, or open
`sandbox/BoxBrain-Isolated.wsb` directly. The feed refreshes every two seconds
and remains strictly read-only. The button is enabled by default only when
`BOXBRAIN_ENVIRONMENT=development`; set
`BOXBRAIN_SANDBOX_LAUNCH_ENABLED=false` to disable it explicitly. The configured
profile can be overridden for development with `BOXBRAIN_SANDBOX_PROFILE`, but
no path is accepted from the dashboard API. Do not expose the local controller
port to another host.

