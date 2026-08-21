# Aurum-Arkmatx Web Node

Shared-host-compatible Aurum edge node and read-only project status surface.

Endpoints:

- `GET /` or `/status` — node status
- `GET /dashboard` — evidence-driven visual command center
- `GET /voice-status` or `/voice-status.txt` — plain-text status for voice chats
- `GET /voice-status.json` — machine-readable form of the same live status
- `POST /uaf` — receive Aurum UAF v0 frames

The dashboard and voice endpoint use the same six-gate human-capability standard:
Defined → Executable → Tested → Seeded → Booted → Used.

The durable repository fallback for assistants that cannot reach the website is
[Aurum Voice Status](../../AURUM_VOICE_STATUS.md).

Requirements: PHP 8+, HTTPS, and writable local storage under `state/`.
No Python, cron, SSH, or persistent daemon is required for the web node itself.
The voice mirror uses public GitHub evidence with a short `/tmp` cache and falls
back to the checked-in status snapshot if outbound GitHub access is unavailable.

Deploy this directory to the desired arkmatx web root or subdirectory. The node
identity remains `Aurum-Arkmatx` regardless of carrier.
