#!/bin/sh
set -eu
CONTROLLER="https://aurum.arkmatx.com"
ROOT="${AURUM_HOME:-$HOME/.aurum}"
mkdir -p "$ROOT"
chmod 700 "$ROOT" 2>/dev/null || true
HOST="$(hostname 2>/dev/null || printf unknown)"
OS="$(uname -s 2>/dev/null || printf unknown)"
ARCH="$(uname -m 2>/dev/null || printf unknown)"
NODE_ID="$(printf '%s-%s-%s' "$HOST" "$OS" "$ARCH" | shasum -a 256 2>/dev/null | awk '{print substr($1,1,16)}')"
if [ -z "${NODE_ID:-}" ]; then NODE_ID="$(date +%s)-$$"; fi
cat > "$ROOT/node.json" <<JSON
{
  "schema": "aurum.node.v0",
  "node_id": "$NODE_ID",
  "name": "$HOST",
  "controller": "$CONTROLLER",
  "carrier": "https",
  "os": "$OS",
  "arch": "$ARCH"
}
JSON
chmod 600 "$ROOT/node.json" 2>/dev/null || true
PAYLOAD="$(printf '{\"schema\":\"aurum.uaf.v0\",\"frame_id\":\"enroll-%s-%s\",\"origin\":\"Aurum-Node-%s\",\"target\":\"Aurum-Arkmatx\",\"intent\":\"node_enroll\",\"state_delta\":{\"node_id\":\"%s\",\"name\":\"%s\",\"os\":\"%s\",\"arch\":\"%s\"},\"provenance\":{\"node\":\"Aurum-Node-%s\",\"created\":%s},\"verification\":{\"content_addressed\":true,\"reversible\":true}}' "$NODE_ID" "$(date +%s)" "$NODE_ID" "$NODE_ID" "$HOST" "$OS" "$ARCH" "$NODE_ID" "$(date +%s)")"
printf '%s' "$PAYLOAD" | curl -fsS -H 'Content-Type: application/json' --data-binary @- "$CONTROLLER/enroll" > "$ROOT/enrollment.json"
printf '\nAurum node enrolled.\nNode: %s\nController: %s\nConfig: %s/node.json\n' "$NODE_ID" "$CONTROLLER" "$ROOT"
