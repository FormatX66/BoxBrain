# Local Windows Copilot Offload

BB-007 adds a review-only Copilot worker lane for three initial task kinds:

- `file_organization`: propose moves and renames from file metadata only;
- `windows_code`: review or draft changes for selected Windows-oriented text files;
- `plugin_code`: review or draft selected plugin code and manifests.

Copilot never receives an open-ended Windows session. BoxBrain prepares a
minimal packet, the operator reviews it, and the exact confirmation
`SEND TO COPILOT` is required before external transmission. Copilot output is
stored as an untrusted proposal; this workflow never applies it.

## Provider choice

The automated adapter uses the official GitHub Copilot CLI. GitHub documents
non-interactive prompts through `copilot -p`, a plan mode, working-directory
selection, tool allowlists, and explicit deny/permission controls:

- [Install GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/install-copilot-cli)
- [Copilot CLI quickstart](https://docs.github.com/en/copilot/how-tos/copilot-cli/cli-getting-started)
- [Copilot CLI command reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference)

The Microsoft Copilot and Microsoft 365 Copilot Windows apps may accept a
reviewed packet manually. BoxBrain does not automate either UI or assume an
undocumented local prompt API.

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
status only—never the objective, prompt, selected contents, Copilot response,
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
BOXBRAIN_COPILOT_OFFLOAD_ENABLED=false
BOXBRAIN_COPILOT_ALLOWED_ROOTS=
BOXBRAIN_COPILOT_TIMEOUT_SECONDS=120
BOXBRAIN_COPILOT_MAX_FILES=100
BOXBRAIN_COPILOT_MAX_FILE_BYTES=32768
BOXBRAIN_COPILOT_MAX_CONTENT_BYTES=131072
BOXBRAIN_COPILOT_MAX_OUTPUT_BYTES=65536
```

On Windows, separate multiple allowed roots with semicolons. Configure the
narrowest practical directories. Do not allow an entire user profile or drive.

Install the CLI through its documented Windows package and authenticate in an
interactive terminal; never place a Copilot token in a work packet or log:

```powershell
winget install GitHub.Copilot
copilot login
```

Only after runtime status reports the CLI installed should an operator set
`BOXBRAIN_COPILOT_OFFLOAD_ENABLED=true`.

## API flow

1. `GET /api/v1/processing/copilot/runtime`
2. `POST /api/v1/processing/copilot/packets`
3. Review the returned prompt, files, exclusions, and hash.
4. `POST /api/v1/processing/copilot/dispatches` with `SEND TO COPILOT`.
5. Review and validate the returned proposal separately.

Example packet preparation:

```json
{
  "task_id": "BB-007",
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
  "confirmation": "SEND TO COPILOT"
}
```
