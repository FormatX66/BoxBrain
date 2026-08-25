# Aurum-Arkmatx Web Node

Shared-host-compatible Aurum edge node and read-only project status surface.

This directory is a BoxBrain integration/evidence mirror. The canonical
Arkmatx.com website, build, and deployment flow is owned by
[ClusterSites](https://github.com/FormatX66/ClusterSites). Arkmatx.com is the
technology-project portal through which this Aurum surface and other
independently owned service backends are exposed.

Hosted endpoints when the Arkmatx PHP deployment is configured:

- `GET /` or `/status` — node status
- `GET /dashboard` — evidence-driven visual command center
- `GET /voice-status` or `/voice-status.txt` — plain-text status for voice chats
- `GET /voice-status.json` — machine-readable form of the same live status
- `POST /uaf` — receive Aurum UAF v0 frames

No-secret repository mirrors, available even when the Arkmatx deployment secrets
are not configured:

- `voice-status.txt` — plain text suitable for voice assistants and raw fetches
- `voice-status.json` — machine-readable six-gate status
- `voice-status/index.html` — browser-readable static status view
- `dashboard.html` — the dashboard source; it can consume the static JSON mirror
- `status` and `nodes` — static read-only fallbacks for dashboard fetches

The dashboard and all voice mirrors use the same six-gate human-capability standard:
Defined → Executable → Tested → Seeded → Booted → Used.

The durable GitHub-connector fallback is
[Aurum Voice Status](../../AURUM_VOICE_STATUS.md).

Requirements for the dynamic node: PHP 8+, HTTPS, and writable local storage under
`state/`. No Python, cron, SSH, or persistent daemon is required by the web node.
The PHP voice mirror uses public GitHub evidence with a short `/tmp` cache and
falls back to the checked-in snapshot when outbound GitHub access is unavailable.

The static mirrors require no hosting password or deployment credential. Deploy
this directory to the desired Arkmatx web root when credentials are restored; the
node identity remains `Aurum-Arkmatx` regardless of carrier.
