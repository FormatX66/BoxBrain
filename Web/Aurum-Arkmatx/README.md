# Aurum-Arkmatx Web Node

Shared-host-compatible Aurum edge node.

Endpoints:
- `GET /` or `/status` — node status
- `POST /uaf` — receive Aurum UAF v0 frames

Requirements: PHP 8+, HTTPS, and writable local storage under `state/`.
No Python, cron, SSH, or persistent daemon required.

Deploy this directory to the desired arkmatx web root or subdirectory. The node identity remains `Aurum-Arkmatx` regardless of carrier.
