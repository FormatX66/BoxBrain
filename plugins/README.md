# BoxBrain plugins

Plugins provide replaceable, capability-scoped boundaries. The controller reads
strict `boxbrain_plugin.json` manifests without importing plugin modules.

The enabled `windows-sandbox-observer` plugin is the first active boundary. Each
status or frame request starts its entrypoint in a separate process, exchanges
one correlated protocol-v1 JSON response, and exits. It can declare only
`observation.describe` and `observation.frame`; it exposes no input operation.
The inert `example-observer` remains manifest-only for discovery tests.

## Current lifecycle

1. Discover and strictly validate the manifest and local entrypoint.
2. Verify protocol, enabled state, target identity, process boundary, and the
   complete approved capability set.
3. Start one child process with a stripped environment and fixed deadline.
4. Correlate plugin, request, target, and protocol identities.
5. Validate the typed response, PNG signature, size limit, and SHA-256 digest.
6. End the process after the single request and fail closed on violations.

The child currently runs under the controller's Windows user. A restricted
service identity, signed packages, persistent authenticated channels, and
quarantine are not implemented yet.

See `docs/PLUGIN_CONTRACT.md` for the exact manifest and message boundary.
