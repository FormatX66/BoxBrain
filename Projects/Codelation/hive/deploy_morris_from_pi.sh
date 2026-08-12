#!/usr/bin/env bash
set -euo pipefail

ROOT="${AURUM_ROOT:-/opt/boxbrain/codelation}"
NODE_NAME="Aurum-Morris"
SSH_OPTS=(-o BatchMode=yes -o IdentitiesOnly=no -o StrictHostKeyChecking=accept-new -o ConnectTimeout=4)

log(){ printf '%s\n' "$*"; }

candidates=()
for h in morris morris.local; do
  getent hosts "$h" >/dev/null 2>&1 && candidates+=("$h") || true
done
while read -r ip _; do
  [ -n "${ip:-}" ] || continue
  name="$(getent hosts "$ip" 2>/dev/null | awk '{print $2}' | head -1 || true)"
  case "${name,,}" in *morris*) candidates+=("$ip");; esac
done < <(ip neigh show 2>/dev/null | awk '$1 ~ /^[0-9]/ {print $1,$NF}')

# de-duplicate while preserving order
uniq=(); declare -A seen=()
for h in "${candidates[@]}"; do
  [[ ${seen[$h]+x} ]] && continue
  seen[$h]=1; uniq+=("$h")
done

if [ ${#uniq[@]} -eq 0 ]; then
  echo 'AURUM_MORRIS_BLOCKED reason=no_morris_peer_identified'
  exit 20
fi

# Existing SSH config/user is preferred. No password guessing or credential spraying.
target=''
for h in "${uniq[@]}"; do
  if ssh "${SSH_OPTS[@]}" "$h" 'exit 0' </dev/null >/dev/null 2>&1; then target="$h"; break; fi
  for u in "${MORRIS_SSH_USER:-}" morris; do
    [ -n "$u" ] || continue
    if ssh "${SSH_OPTS[@]}" "$u@$h" 'exit 0' </dev/null >/dev/null 2>&1; then target="$u@$h"; break 2; fi
  done
done

if [ -z "$target" ]; then
  echo 'AURUM_MORRIS_BLOCKED reason=peer_found_but_no_existing_key_authorization'
  exit 21
fi

# Detect Windows vs POSIX over the already-authorized channel.
if ssh "${SSH_OPTS[@]}" "$target" 'powershell.exe -NoProfile -NonInteractive -Command "$PSVersionTable.PSVersion.ToString()"' </dev/null >/dev/null 2>&1; then
  cat "$ROOT/hive/install_morris_node.ps1" | ssh "${SSH_OPTS[@]}" "$target" 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command -'
else
  tar -C "$ROOT" -cf - aurum_hive.py slush_query.py state_diff.py capability_registry.py human_projection.py autonomous_cycle.py intrinsic_policy.py hive_event_integration.py 2>/dev/null \
    | ssh "${SSH_OPTS[@]}" "$target" 'set -eu; umask 077; mkdir -p "$HOME/.aurum"; tar -C "$HOME/.aurum" -xf -; printf "%s\n" "AURUM_NODE_READY name=Aurum-Morris path=$HOME/.aurum"'
fi

printf 'AURUM_MORRIS_DEPLOYED target=%s node=%s\n' "$target" "$NODE_NAME"
