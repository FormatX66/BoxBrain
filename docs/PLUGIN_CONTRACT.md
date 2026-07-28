# Plugin Contract

Each plugin lives in its own directory with a strict `boxbrain_plugin.json`
manifest and a local Python entrypoint. The controller validates manifests but
never imports plugin code into its own process.

## Manifest fields

| Field | Meaning |
|---|---|
| `id` | Stable reverse-domain identifier |
| `name` | Operator-facing name |
| `version` | Semantic `major.minor.patch` version |
| `description` | One-sentence purpose |
| `enabled` | Explicit activation state |
| `protocol_version` | Supported local protocol; currently `1` |
| `entrypoint` | Python filename inside the plugin directory |
| `capabilities` | Unique allowlist of typed operations |
| `process_boundary` | `manifest-only` or `out-of-process` |
| `target_id` | Optional allowlisted target identity |

Unknown fields, path separators in entrypoints, missing entrypoints, duplicate
capabilities, malformed identifiers, and unsupported protocol versions make a
manifest undiscoverable.

## Observation protocol version 1

The Windows Sandbox observer starts as a new process for each status or frame
request. The controller sends exactly one JSON line on standard input:

```json
{
  "protocol_version": "1",
  "plugin_id": "boxbrain.windows-sandbox-observer",
  "request_id": "correlation UUID",
  "operation": "describe",
  "payload": {}
}
```

A frame request changes `operation` to `capture_frame` and includes exactly one
strict `policy` object:

```json
{
  "schema_version": 1,
  "max_frame_width": 1280,
  "max_frame_bytes": 8388608,
  "redaction_regions": [],
  "evidence_retention": {
    "mode": "none",
    "max_frames": 0,
    "max_age_seconds": 0
  }
}
```

Redaction coordinates are normalized to the resized frame and may use only a
black fill. The child validates the policy independently and reports the applied
redaction count and width limit in its frame envelope.

The plugin returns exactly one JSON line with the same protocol, plugin, and
request identities; an `ok` flag; and either a typed `result` or a short error.
The controller rejects mismatched identities, undeclared capabilities, extra
output, invalid schemas, timeouts, oversized responses, non-PNG frames, frames
larger than 8 MiB, and frame digest mismatches. The checked-in observer scales
captures to at most 1280 pixels wide before encoding. It rejects frames larger
than the policy's 8 MiB ceiling. The controller rejects a reported redaction
count or width that does not match the policy it sent.

The approved observer capabilities are only:

- `observation.describe`
- `observation.frame`

There is no input, clipboard, file, shell, launch, or arbitrary-process
operation in the plugin protocol. Opening the fixed Sandbox profile remains a
separate controller capability guarded by the emergency stop and audit log.

## Process boundary

The child receives a minimal environment that excludes the controller API token
and provider credentials. It has a four-second deadline, a 12 MiB response
limit, and exits after one request. This prevents plugin state from living in
the controller process and makes protocol violations fail closed. The controller
allows one frame child at a time and responds with HTTP 429 plus `Retry-After`
when a capture is already in progress. Neither side persists frame bytes.

This is process separation, not a lower-privilege Windows sandbox. The plugin
currently runs as the same Windows user as the controller and uses checked-in
code. A restricted service identity, package signatures, authenticated
persistent channels, cancellation, and quarantine remain future hardening.
