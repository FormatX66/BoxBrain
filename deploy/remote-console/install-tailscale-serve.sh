#!/usr/bin/env bash
set -euo pipefail

CONTROLLER_PORT="${BOXBRAIN_CONTROLLER_PORT:-8000}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer as root (sudo)." >&2
  exit 1
fi

if ! command -v tailscale >/dev/null 2>&1; then
  echo "Tailscale is not installed. Install and authenticate Tailscale first:" >&2
  echo "  curl -fsSL https://tailscale.com/install.sh | sh" >&2
  echo "  sudo tailscale up" >&2
  exit 2
fi

if ! tailscale status >/dev/null 2>&1; then
  echo "Tailscale is installed but this node is not connected. Run: sudo tailscale up" >&2
  exit 3
fi

# BoxBrain remains loopback/local; Tailscale terminates HTTPS and proxies to it.
tailscale serve --bg "http://127.0.0.1:${CONTROLLER_PORT}"

echo
echo "BoxBrain One remote console is enabled inside your tailnet."
tailscale serve status

echo
echo "Security notes:"
echo "- Keep BOXBRAIN_API_TOKEN enabled (32+ random characters)."
echo "- Do not bind the controller directly to a public interface."
echo "- Restrict this Pi/node with Tailscale Grants/ACLs to your approved users/devices."
echo "- Use 'tailscale serve reset' to remove the remote-console proxy."
