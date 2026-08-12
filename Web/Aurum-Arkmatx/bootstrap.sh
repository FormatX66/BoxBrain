#!/bin/sh
set -eu
CONTROLLER="https://arkmatx.com/aurum/index.php"
PORTAL="https://aurum.arkmatx.com"
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
  "portal": "$PORTAL",
  "carrier": "https-outbound",
  "os": "$OS",
  "arch": "$ARCH"
}
JSON
chmod 600 "$ROOT/node.json" 2>/dev/null || true
NOW="$(date +%s)"
ENROLL="$(printf '{\"schema\":\"aurum.uaf.v0\",\"frame_id\":\"enroll-%s-%s\",\"origin\":\"Aurum-Node-%s\",\"target\":\"Aurum-Arkmatx\",\"intent\":\"node_enroll\",\"state_delta\":{\"node_id\":\"%s\",\"name\":\"%s\",\"os\":\"%s\",\"arch\":\"%s\",\"carrier\":\"https-outbound\"},\"provenance\":{\"node\":\"Aurum-Node-%s\",\"created\":%s},\"verification\":{\"content_addressed\":true,\"reversible\":true}}' "$NODE_ID" "$NOW" "$NODE_ID" "$NODE_ID" "$HOST" "$OS" "$ARCH" "$NODE_ID" "$NOW")"
printf '%s' "$ENROLL" | curl -fsS -H 'Content-Type: application/json' --data-binary @- "$CONTROLLER" > "$ROOT/enrollment.json"
NOW="$(date +%s)"
HEARTBEAT="$(printf '{\"schema\":\"aurum.uaf.v0\",\"frame_id\":\"heartbeat-%s-%s\",\"origin\":\"Aurum-Node-%s\",\"target\":\"Aurum-Arkmatx\",\"intent\":\"node_heartbeat\",\"state_delta\":{\"node_id\":\"%s\",\"carrier\":\"https-outbound\"},\"provenance\":{\"node\":\"Aurum-Node-%s\",\"created\":%s},\"verification\":{\"content_addressed\":true,\"reversible\":true}}' "$NODE_ID" "$NOW" "$NODE_ID" "$NODE_ID" "$NODE_ID" "$NOW")"
printf '%s' "$HEARTBEAT" | curl -fsS -H 'Content-Type: application/json' --data-binary @- "$CONTROLLER" > "$ROOT/heartbeat.json"
printf '\nAurum node enrolled and heartbeat confirmed.\nNode: %s\nController: %s\nConfig: %s/node.json\n' "$NODE_ID" "$CONTROLLER" "$ROOT"
