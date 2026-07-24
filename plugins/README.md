# BoxBrain plugins

Plugins will provide replaceable transports and capabilities such as remote
viewing, input execution, vision providers, or model providers.

The alpha registry only reads `boxbrain_plugin.json` manifests. It does not
import or execute plugin code. The example plugin is intentionally inert.

## Planned lifecycle

1. Discover and validate a manifest.
2. Verify compatibility and an administrator-approved capability list.
3. Start the plugin out of process with a restricted service identity.
4. Exchange versioned messages over a local authenticated channel.
5. Record every requested and completed action in the audit log.
6. Stop and quarantine a plugin that violates its declared contract.

See `docs/PLUGIN_CONTRACT.md` for the initial manifest schema and boundaries.

