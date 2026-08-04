# BoxBrain

BoxBrain is a modular controller for connecting cloud AI planning to an
isolated computer lab. The first milestone is deliberately small: a Flutter
mission-control UI, a Python/FastAPI controller API, a plugin boundary, policy
profiles, an audit-friendly task queue, and a restricted Kali Pi edge agent.

This repository is an initial alpha. It does **not** autonomously execute
keyboard, mouse, remote-desktop, or arbitrary shell actions. Its optional
model-processing endpoint exposes no side-effect tools. The separate Kali Pi
diagnostic executor runs only fixed read-only commands after an explicit `RUN`
approval.

## Repository layout

```text
BoxBrain/
|-- ui/                    Flutter dashboard source
|-- controller/            FastAPI controller service
|-- edge/kali-pi-agent/    Deployable Kali Pi edge agent
|-- plugins/               Plugin contract and inert example plugin
|-- docs/                  Product, architecture, security, and setup notes
|-- installer/             Local setup and validation scripts
|-- tests/                 Cross-component test notes
|-- Admin/                 Ecosystem roadmap, indexes, decisions, and changes
|-- Architecture/          Cross-project architecture and integrations
|-- Projects/              Project registry and dependency links
|-- Agents/                Canonical agent role definitions
`-- SessionHandoffs/       Human and agent continuity records
```

## Ecosystem coordination

This repository is also the canonical knowledge and coordination layer for the
BoxBrain ecosystem. It indexes projects and shared decisions without copying
the code or detailed technical documentation of separate implementation
repositories.

- [Repository index](Admin/RepositoryIndex.md)
- [Project index](Projects/README.md)
- [Master TODO](Admin/MasterTODO.md)
- [Roadmap](Admin/Roadmap.md)
- [Decision index](Admin/Decisions.md)
- [Change index](Admin/ChangeLog.md)
- [Session index](Admin/SessionIndex.md)
- [Cross-project architecture](Architecture/SystemArchitecture.md)
- [Knowledge and execution data flow](Architecture/DataFlow.md)
- [Agent role index](Agents/README.md)
- [Prompt library](PromptLibrary/README.md)
- [Templates](Templates/README.md)
- [Session handoffs](SessionHandoffs/README.md)
- [Archive policy](Archive/README.md)

BoxBrain core code remains canonical in this repository. Separately registered
projects, including BrainConnect, remain authoritative for their own code and
detailed documentation. A document has one canonical location; other locations
link to it.

## Technical reference

- [Product requirements](docs/PRD.md)
- [Application architecture](docs/ARCHITECTURE.md)
- [Application roadmap](docs/ROADMAP.md)
- [Plugin contract](docs/PLUGIN_CONTRACT.md)
- [Agent build brief](docs/AGENT_BUILD_BRIEF.md)
- [Controller](controller/README.md)
- [Flutter dashboard](ui/README.md)
- [Plugin implementations](plugins/README.md)
- [Kali Pi edge agent](edge/kali-pi-agent/README.md)
- [Hyper-V Windows lab](sandbox/hyperv/README.md)
- [Cross-component tests](tests/README.md)
- [ChatGPT write-boundary test notes](CHATGPT_WRITE_TEST.md)
- [Memory priority stack](memory-priority-stack/README.md)
- [Orchestrator memory prompt](memory-priority-stack/docs/ORCHESTRATOR_MEMORY_PROMPT.md)

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

Use the dashboard's **Agents** destination to process voice or chat intake,
review the ten-agent crew, inspect memory and task totals, and optionally enable
model reasoning. Local processing is the default and requires no provider
tokens. The same Agents destination includes the local ChatGPT organizer, which
preserves current project membership and proposes folders for loose chats
without scraping browser storage or moving anything in ChatGPT. See
[docs/CHATGPT_ORGANIZER.md](docs/CHATGPT_ORGANIZER.md).

Use **Fleet** to import authorized targets, register one durable identity per
machine, catalog capabilities, and run the resumable provisioning checklist.
External Gmail, Drive, GitHub, and CAPTCHA steps remain operator-controlled;
BoxBrain stores no account passwords or recovery secrets. The dashboard also
shows the canonical twelve-agent system roster. See
[docs/BOXBRAIN_ARCHITECTURE_V1.md](docs/BOXBRAIN_ARCHITECTURE_V1.md).

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

For full RDP listener, durable identity, Pi-only networking, and clean
checkpoint tests, use the separate
[Hyper-V Windows lab](sandbox/hyperv/README.md). It is disposable, contains no
personal account or files, and remains powered off at its clean baseline until
an explicitly reviewed experiment starts.

### 4. Kali Pi edge agent

The consolidated Kali Pi implementation lives in `edge/kali-pi-agent`. It is a
restricted edge agent for authorized read-only diagnostics and private-scope
assessment; it is not a second controller. Start the existing SSH local-forward
to port `8787` and the main dashboard will show the agent's sanitized connection,
version, target-count, and recommendation-count summary.

The controller accepts only a loopback agent URL and never copies Pi credentials
or raw diagnostic reports into its API. See [docs/EDGE_AGENT.md](docs/EDGE_AGENT.md)
for the architecture, tunnel command, USB-C and SSH/Wi-Fi target enrollment, and safe Pi upgrade
path.

An optional live Pi screen is also available through a loopback-only
VNC/WebSocket transport and key-only SSH tunnel. It can be opened manually or
by a current-user Windows connection watcher; neither path is enabled by the
normal edge-agent install or controls enrolled targets. See
[the edge-agent console setup](edge/kali-pi-agent/README.md#optional-live-pi-screen).

### 5. Connect an authorized host

Open **Target** and use **Add target** to register a private, loopback, or
link-local host. Supported operator-controlled sessions are USB-C SSH, SSH,
Windows Remote Management, Windows Remote Desktop, and explicitly acknowledged
lab-only Telnet. Use **Test** for a TCP reachability check, then **Open session**
and type `OPEN` to launch the operating-system client.

BoxBrain stores target metadata, not passwords. SSH uses the agent or the
dedicated Pi key, WinRM uses the current Windows identity, and RDP prompts
interactively. Telnet is plaintext and requires its separate exact warning
phrase. The emergency stop blocks every session launch. This target manager
does not give queued tasks a shell or autonomous host control.

#### Approval-gated AI diagnostics

The built-in Kali Pi target also exposes **AI check**. Describe what to inspect;
the model may select only `system_health`, `disk_usage`, `memory_usage`, or
`uptime`. Review the typed proposal, then type `RUN` to execute its fixed
read-only SSH diagnostic. User text never becomes shell input. Proposals expire,
output is capped and not retained as evidence, and the emergency stop blocks
execution. General targets and queued tasks cannot use this executor.

### 6. Queue and audit tasks

Use **Tasks** to queue a goal for the connected Sandbox. Tasks are stored in
`controller/data/boxbrain.sqlite3`, survive controller restarts, and create an
append-only event visible under **Logs**. New events arrive over an authenticated
server-sent event stream with sequence-based resume and automatic reconnect.
Queueing records intent only; the autonomous task executor remains disabled.

### 7. Emergency stop

Use the red stop control from any dashboard screen to block Sandbox launches
and future executor actions. The state survives controller restarts and every
engage/reset request is audited. Read-only observation remains available while
stopped. Resetting requires typing `RESET` in the confirmation dialog.

### 8. Verify

```powershell
.\installer\validate-project.ps1

# Also compile the production web dashboard.
.\installer\validate-project.ps1 -Mode Full
```

The quick runner resolves Flutter packages once, then batches controller tests,
Kali Pi edge-agent tests, Flutter analysis, and Flutter tests into one local
command. It uses local CPU
and does not consume GitHub Actions minutes. The hosted GitHub workflow is
manual-only; use **Run workflow** when an intentional remote check is useful.
Choose `quick` for tests or `full` to include the production web build.

The scripts in [installer/README.md](installer/README.md) can create and remove
the Current User development certificate, generate the local token, build and
serve the authenticated dashboard, start the loopback controller, and run a
read-only security check without printing the credential.

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for setup details,
[docs/EDGE_AGENT.md](docs/EDGE_AGENT.md) for the Kali Pi integration, and
[docs/SECURITY.md](docs/SECURITY.md) before adding any executor.
