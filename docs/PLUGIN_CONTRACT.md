# Plugin Contract Draft

Each plugin lives in its own directory and includes a
`boxbrain_plugin.json` manifest.

## Required manifest fields

| Field | Meaning |
|---|---|
| `id` | Stable reverse-domain identifier |
| `name` | Operator-facing name |
| `version` | Semantic version |
| `description` | One-sentence purpose |
| `enabled` | Initial activation state |
| `entrypoint` | Future out-of-process entrypoint |
| `capabilities` | Explicit allowlist of typed operations |

The alpha reads only the first five fields into its public API. It does not
import entrypoints.

## Planned rules

- Plugins run outside the controller process.
- A plugin receives only configuration and credentials needed for its declared
  capability.
- Every message carries plugin, task, target, correlation, and schema versions.
- Timeouts, cancellation, and idempotency are required.
- Raw shell execution is not a general plugin capability.
- Enabling a plugin is an explicit operator action.

