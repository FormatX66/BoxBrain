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

### 1. Flutter dashboard

Flutter must be available on `PATH`. From `ui/`, generate the missing platform
runners once, then run the app:

```powershell
flutter create --project-name boxbrain_ui --platforms=windows,linux,web .
flutter pub get
flutter run -d windows
```

The source is already present under `ui/lib`; `flutter create` is only needed
to add Flutter's generated Windows, Linux, and web runner files.

### 2. Controller API

From `controller/`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m uvicorn boxbrain_controller.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the API explorer.

### 3. Verify

```powershell
cd controller
python -m pytest

cd ..\ui
flutter analyze
flutter test
```

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for setup details and
[docs/SECURITY.md](docs/SECURITY.md) before adding any executor.
