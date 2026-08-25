# Aurum Farmer

Farmer turns an Aurum/BoxBrain request into one durable job and keeps advancing
it after a chat response, app session, runner process, or supervisor process
ends. The ledger, not conversation memory, is authoritative.

## State machine

```text
RECEIVED -> PLANNED -> READY -> RUNNING -> VERIFYING -> SUCCEEDED
                              |             |
                              |             +-> RETRYING / RECOVERING
                              +-> WAITING / BLOCKED_HUMAN / FAILED_FINAL
```

Every state change is validated and hash-chained. Evidence and event rows are
append-only. Every attempt receives an HMAC-sealed receipt; success additionally
requires every declared evidence kind to be present, verified, and sealed.

## Executors

- `github_workflow` dispatches and reads back a GitHub Actions run.
- `chat_to_git` sends one validated request through
  `FormatX66/Chat-to-Git-Pipeline`, then verifies the feedback issue, Actions
  result, and downloadable receipt artifact.
- `local_process` runs only an exact executable configured in the local
  allowlist, never a shell string.
- `evidence_file` waits for and hashes an external/physical receipt.
- `human_boundary` records a real human-only edge.
- `noop` is an internal end-to-end service canary.

If one branch fails, Farmer quarantines it and promotes the next warm safe
branch. Transient retries are bounded. A stable failure is replayed only after a
named state, evidence, implementation, environment, dependency, hypothesis, or
authority dimension changes.

## Local use

From the repository root:

```powershell
$env:PYTHONPATH = (Resolve-Path .\Projects\AurumFarmer).Path
python -m aurum_farmer --config .\work\farmer\farmer.json init --root .\work\farmer
python -m aurum_farmer --config .\work\farmer\farmer.json canary
python -m aurum_farmer --config .\work\farmer\farmer.json run --once
python -m aurum_farmer --config .\work\farmer\farmer.json status
```

Submit any job as a JSON object with a `goal` and complete `branches` array:

```powershell
python -m aurum_farmer --config .\work\farmer\farmer.json submit --file job.json
```

Route a bounded request through Chat-to-Git under Farmer:

```powershell
python -m aurum_farmer --config .\work\farmer\farmer.json `
  submit-chat-to-git --prompt "Check the repository status" `
  --dedupe-key "chat-to-git-status-current-main"
```

## Persistent Windows install

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\install-aurum-farmer.ps1
```

The installer creates an immutable versioned application release under the
current user's local application data, preserves all older releases, keeps the
ledger and signing material in a separate runtime directory, registers a
current-user `Aurum Farmer` scheduled task with restart-on-failure, starts it,
and verifies the loopback health endpoint. It does not expose a firewall port or
copy a provider credential.

The local API binds to `127.0.0.1:19466`. `/health` is public only on loopback;
job reads/writes require the bearer token stored in the ACL-restricted runtime
token file.

Unregister the task without deleting durable state:

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\uninstall-aurum-farmer.ps1
```

## Verification

```powershell
$env:PYTHONPATH = (Resolve-Path .\Projects\AurumFarmer).Path
python -m unittest discover -s .\Projects\AurumFarmer\tests -v
```

The suite covers restart/resume, expired-runner recovery, bounded retries,
human boundaries, evidence-gated completion, LKG preservation, branch ranking,
deduplication, append-only storage, and the Chat-to-Git adapter contract.
