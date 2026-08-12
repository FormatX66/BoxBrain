#!/usr/bin/env bash
set -euo pipefail

ROOT="${AURUM_ROOT:-/opt/boxbrain/codelation}"
NODE="$ROOT/hive/aurum_node.py"
NODE_NAME="Aurum-Morris"
SSH_OPTS=(-o BatchMode=yes -o IdentitiesOnly=no -o StrictHostKeyChecking=accept-new -o ConnectTimeout=4)
SCP_OPTS=(-o BatchMode=yes -o IdentitiesOnly=no -o StrictHostKeyChecking=accept-new -o ConnectTimeout=4)

[ -f "$NODE" ] || { echo 'AURUM_MORRIS_BLOCKED reason=node_payload_missing'; exit 19; }

candidates=()
for h in morris morris.local; do
  getent hosts "$h" >/dev/null 2>&1 && candidates+=("$h") || true
done
while read -r ip _; do
  [ -n "${ip:-}" ] || continue
  name="$(getent hosts "$ip" 2>/dev/null | awk '{print $2}' | head -1 || true)"
  case "${name,,}" in *morris*) candidates+=("$ip");; esac
done < <(ip neigh show 2>/dev/null | awk '$1 ~ /^[0-9]/ {print $1,$NF}')

uniq=(); declare -A seen=()
for h in "${candidates[@]}"; do
  [[ ${seen[$h]+x} ]] && continue
  seen[$h]=1; uniq+=("$h")
done

if [ ${#uniq[@]} -eq 0 ]; then
  echo 'AURUM_MORRIS_BLOCKED reason=no_morris_peer_identified'
  exit 20
fi

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

if ssh "${SSH_OPTS[@]}" "$target" 'powershell.exe -NoProfile -NonInteractive -Command "$PSVersionTable.PSVersion.ToString()"' </dev/null >/dev/null 2>&1; then
  winroot="$(ssh "${SSH_OPTS[@]}" "$target" 'powershell.exe -NoProfile -NonInteractive -Command "$p=Join-Path $env:LOCALAPPDATA '\''BoxBrain\AurumMorris'\''; New-Item -ItemType Directory -Force -Path $p | Out-Null; $p.Replace('\''\'\'', '\''/'\'')"' | tr -d '\r')"
  [ -n "$winroot" ] || { echo 'AURUM_MORRIS_BLOCKED reason=windows_install_path_unavailable'; exit 22; }
  scp "${SCP_OPTS[@]}" "$NODE" "${target}:$winroot/aurum_node.py"
  ssh "${SSH_OPTS[@]}" "$target" 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$root=Join-Path $env:LOCALAPPDATA '\''BoxBrain\AurumMorris'\''; $node=Join-Path $root '\''aurum_node.py'\''; $python=(Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source; if(-not $python){$python=(Get-Command python.exe -ErrorAction SilentlyContinue).Source}; if(-not $python){throw '\''Python runtime unavailable'\''}; $args='\''"'\''+$node+'\''" --root "'\''+$root+'\''" --name Aurum-Morris run --interval 2'\''; New-ItemProperty -Path '\''HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'\'' -Name '\''AurumMorris'\'' -Value ('\''"'\''+$python+'\''" '\''+$args) -PropertyType String -Force | Out-Null; Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -like '\''*aurum_node.py*Aurum-Morris*run*'\''} | ForEach-Object {Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue}; Start-Process -FilePath $python -ArgumentList $args -WindowStyle Hidden; $check=(Get-Command python.exe -ErrorAction SilentlyContinue).Source; if(-not $check){$check=$python}; & $check $node --root $root --name Aurum-Morris cycle | Out-Null; & $check $node --root $root --name Aurum-Morris status"'
else
  ssh "${SSH_OPTS[@]}" "$target" 'set -eu; umask 077; mkdir -p "$HOME/.aurum"'
  scp "${SCP_OPTS[@]}" "$NODE" "${target}:~/.aurum/aurum_node.py"
  ssh "${SSH_OPTS[@]}" "$target" 'set -eu; command -v python3 >/dev/null; pkill -f "aurum_node.py.*Aurum-Morris.*run" 2>/dev/null || true; nohup python3 "$HOME/.aurum/aurum_node.py" --root "$HOME/.aurum/state" --name Aurum-Morris run --interval 2 >"$HOME/.aurum/aurum.log" 2>&1 </dev/null & python3 "$HOME/.aurum/aurum_node.py" --root "$HOME/.aurum/state" --name Aurum-Morris cycle >/dev/null; python3 "$HOME/.aurum/aurum_node.py" --root "$HOME/.aurum/state" --name Aurum-Morris status'
fi

printf 'AURUM_MORRIS_DEPLOYED target=%s node=%s\n' "$target" "$NODE_NAME"
