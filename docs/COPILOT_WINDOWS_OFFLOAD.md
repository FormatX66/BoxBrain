# Local Windows Tasks with GitHub Copilot

BB-008 adds a review-only **GitHub Copilot CLI** worker lane for three initial
task kinds. In this document, "Windows" describes the local task environment;
it does not mean the Microsoft Copilot app for Windows.

- `file_organization`: propose moves and renames from file metadata only;
- `windows_code`: review or draft changes for selected Windows-oriented text files;
- `plugin_code`: review or draft selected plugin code and manifests.

GitHub Copilot never receives an open-ended Windows session. BoxBrain prepares a
minimal packet, the operator reviews it, and the exact confirmation
`SEND TO GITHUB COPILOT` is required before external transmission. GitHub
GitHub Copilot output is stored as an untrusted proposal; this workflow never applies
it.

## Provider identity

BoxBrain uses stable provider IDs and never labels either surface merely
"Copilot":

| Provider ID | Display name | Vendor | BoxBrain access |
| --- | --- | --- | --- |
| `github-copilot-cli` | GitHub Copilot CLI | GitHub | Guarded automated plan-mode dispatch |
| `windows-copilot-app` | Microsoft Copilot (Windows app) | Microsoft | Detection and manual copy only; no automated dispatch |

`GET /api/v1/processing/copilot/providers` returns these as separate typed
records. The Windows detector reads the current user's registered
`Microsoft.Copilot` app package without launching the app or inspecting its
sign-in state.

Microsoft documents the standalone [Microsoft Copilot app for Windows](https://support.microsoft.com/en-US/microsoft-copilot/getting-started-with-microsoft-copilot)
as a conversational app using a personal Microsoft account. It is distinct
from GitHub Copilot and from the Microsoft 365 Copilot app.

## Automated provider

The automated adapter uses the official GitHub Copilot CLI. GitHub documents
non-interactive prompts through `copilot -p`, a plan mode, working-directory
selection, tool allowlists, and explicit deny/permission controls:

- [Install GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/install-copilot-cli)
- [Copilot CLI quickstart](https://docs.github.com/en/copilot/how-tos/copilot-cli/cli-getting-started)
- [Copilot CLI command reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference)

The Microsoft Copilot Windows app may accept reviewed text manually. BoxBrain
does not automate its UI or assume an undocumented local prompt API. Microsoft
365 Copilot is a third, separate product and is outside this BB-008 adapter.

## Safety boundary

Preparation is limited to configured roots. Paths must be relative to the
selected root, are resolved before access, and may not escape through `..` or a
symlink. The default allowed root is the BoxBrain repository.

File-organization packets include relative path, size, modification time, and
extension-oriented metadata. They do not read or transmit file contents and
their output contract forbids deletion, overwrite, or execution.

Code and plugin packets include only explicitly selected UTF-8 files with an
allowlisted extension. BoxBrain excludes:

- `.env` files and credential/private-key filenames;
- `.pem`, `.key`, `.p12`, and `.pfx` files;
- `.git`, `.ssh`, `.aws`, `.azure`, `.copilot`, virtual environments,
  dependency trees, and generated caches;
- files containing private-key markers, provider-token patterns, or likely
  password/API-key/client-secret assignments;
- files exceeding the per-file or total packet bounds.

Rejected filenames and generic reasons may appear in the review packet, but
their contents do not. Audit events contain IDs, counts, hashes, duration, and
status only—never the objective, prompt, selected contents, GitHub Copilot response,
or credentials.

## Isolated dispatch

BoxBrain invokes the CLI with a fixed argument vector and no shell. The working
directory contains only `request.md` and its integrity-checked packet record.
The CLI starts in plan mode with:

- only the `view` tool available;
- read permission limited to `request.md`;
- built-in MCP servers disabled;
- repository custom instructions disabled;
- system temporary-directory access disabled;
- remote access and remote export disabled;
- auto-update, autopilot, shell, write, and web capabilities unavailable.

The returned plan, patch, or move manifest is written to `response.json` next
to the packet. Applying changes is deliberately outside this service and must
go through normal BoxBrain/human review, tests, and rollback controls.

## Configuration

Dispatch is disabled by default. Relevant environment settings are:

```text
BOXBRAIN_GITHUB_COPILOT_OFFLOAD_ENABLED=false
BOXBRAIN_GITHUB_COPILOT_ALLOWED_ROOTS=
BOXBRAIN_GITHUB_COPILOT_TIMEOUT_SECONDS=120
BOXBRAIN_GITHUB_COPILOT_MAX_FILES=100
BOXBRAIN_GITHUB_COPILOT_MAX_FILE_BYTES=32768
BOXBRAIN_GITHUB_COPILOT_MAX_CONTENT_BYTES=131072
BOXBRAIN_GITHUB_COPILOT_MAX_OUTPUT_BYTES=65536
```

On Windows, separate multiple allowed roots with semicolons. Configure the
narrowest practical directories. Do not allow an entire user profile or drive.

Install the CLI through its documented Windows package and authenticate in an
interactive terminal; never place GitHub Copilot credentials in a work packet or log:

```powershell
winget install GitHub.Copilot
copilot login
```

Only after runtime status reports the CLI installed should an operator set
`BOXBRAIN_GITHUB_COPILOT_OFFLOAD_ENABLED=true`.

## API flow

1. `POST /api/v1/processing/workflows/optimize` to obtain an advisory,
   provider-specific workflow with no action taken.
2. `GET /api/v1/processing/copilot/providers` and verify the exact provider ID.
3. `GET /api/v1/processing/copilot/runtime` and verify that the automated
   provider is `github-copilot-cli`.
4. `POST /api/v1/processing/copilot/packets`.
5. Review the returned provider, prompt, files, exclusions, and hash.
6. `POST /api/v1/processing/copilot/dispatches` with
   `SEND TO GITHUB COPILOT`.
7. Review and validate the returned proposal separately.

Example packet preparation:

```json
{
  "task_id": "BB-008",
  "description": "Review the selected PowerShell inventory helper",
  "kind": "windows_code",
  "root": ".",
  "paths": ["installer/inventory.ps1"]
}
```

Example dispatch:

```json
{
  "packet_id": "00000000-0000-0000-0000-000000000000",
  "confirmation": "SEND TO GITHUB COPILOT"
}
```
