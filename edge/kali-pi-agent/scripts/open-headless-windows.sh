#!/bin/sh
set -eu

state_directory=${BOXBRAIN_STATE_DIR:-/var/lib/boxbrain}
identity_file=${BOXBRAIN_TARGET_IDENTITY:-$state_directory/identity/target_ed25519}
known_hosts=$state_directory/identity/target_known_hosts

pause_and_exit() {
    status=$1
    printf '\nPress Enter to close this BoxBrain terminal.'
    read -r _unused || true
    exit "$status"
}

if ! target=$(
    /usr/local/bin/boxbrainctl targets |
        python3 -c '
import ipaddress
import json
import sys

items = json.load(sys.stdin)
matches = [
    item
    for item in items
    if item.get("status") == "connected"
    and item.get("interface") == "usb0"
    and item.get("user") == "boxbrain-link"
]
if len(matches) != 1:
    raise SystemExit(
        f"Expected exactly one connected USB Windows target; found {len(matches)}."
    )
address = ipaddress.ip_address(str(matches[0].get("address", "")))
if address not in ipaddress.ip_network("10.12.194.0/24") or address == ipaddress.ip_address("10.12.194.1"):
    raise SystemExit("The connected target is outside the dedicated USB subnet.")
print(address)
'
); then
    printf '\nNo unambiguous verified USB target is available.\n' >&2
    printf 'Use BoxBrain enrollment and host-key verification before opening SSH.\n' >&2
    pause_and_exit 1
fi

printf 'BoxBrain restricted SSH -> boxbrain-link@%s\n' "$target"
printf 'This session is non-administrator and uses the pinned Pi trust store.\n\n'

set +e
sudo -n -u boxbrain /usr/bin/ssh \
    -T \
    -i "$identity_file" \
    -o BatchMode=yes \
    -o ConnectTimeout=8 \
    -o IdentitiesOnly=yes \
    -o StrictHostKeyChecking=yes \
    -o "UserKnownHostsFile=$known_hosts" \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    "boxbrain-link@$target" \
    "powershell.exe -NoLogo -NoProfile"
status=$?
set -e

printf '\nBoxBrain target SSH exited with status %s.\n' "$status"
pause_and_exit "$status"
