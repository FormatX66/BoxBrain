#!/bin/sh
set -eu
umask 077

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this configuration helper with sudo." >&2
    exit 1
fi
if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
    echo "Usage: boxbrain-drive-configure DEVICE_ID ROOT_FOLDER_ID [EXPECTED_EMAIL]" >&2
    exit 2
fi

device_id=$1
root_folder_id=$2
expected_email=${3:-boxbrainprime@gmail.com}
remote=boxbrain-drive
config=/var/lib/boxbrain/identity/rclone.conf
environment=/etc/boxbrain/boxbrain.env

case "$device_id" in
    ''|*[!A-Za-z0-9._-]*)
        echo "DEVICE_ID may contain only letters, digits, dot, underscore, and hyphen." >&2
        exit 2
        ;;
esac
case "$root_folder_id" in
    ''|*[!A-Za-z0-9_-]*)
        echo "ROOT_FOLDER_ID is invalid." >&2
        exit 2
        ;;
esac
case "$expected_email" in
    *@*.*) ;;
    *) echo "EXPECTED_EMAIL is invalid." >&2; exit 2 ;;
esac
if ! command -v rclone >/dev/null 2>&1; then
    echo "rclone is required but was not found. Install a verified upstream build first." >&2
    exit 1
fi

printf '%s\n' \
    "This one-time step will authorize rclone for Google Drive." \
    "Use the browser account: $expected_email" \
    "The helper will create the remote exactly as: $remote" \
    "Provider: Google Drive (fixed)" \
    "Scope: drive (fixed)" \
    "Root folder ID: $root_folder_id" \
    "The token will be stored at $config with boxbrain:boxbrain 0600 permissions." \
    "Downloaded patches will be staged and checksum-verified, never auto-executed."
printf 'Type CONFIGURE DRIVE to continue: '
IFS= read -r confirmation
if [ "$confirmation" != "CONFIGURE DRIVE" ]; then
    echo "Drive configuration cancelled." >&2
    exit 1
fi

temporary=$(mktemp /var/lib/boxbrain/identity/.rclone.conf.XXXXXX)
cleanup() {
    rm -f "$temporary"
}
trap cleanup EXIT HUP INT TERM

rclone config create "$remote" drive \
    scope=drive \
    root_folder_id="$root_folder_id" \
    config_is_local=true \
    --no-output \
    --config "$temporary"
python3 - "$temporary" "$remote" "$root_folder_id" <<'PY'
import configparser
import sys

config_path, remote, expected_root = sys.argv[1:]
parser = configparser.ConfigParser(interpolation=None)
with open(config_path, encoding="utf-8") as stream:
    parser.read_file(stream)

if not parser.has_section(remote):
    raise SystemExit(f"The {remote} remote is missing.")
expected = {
    "type": "drive",
    "scope": "drive",
    "root_folder_id": expected_root,
}
for name, value in expected.items():
    if parser.get(remote, name, fallback="") != value:
        raise SystemExit(f"The configured Drive {name} did not match.")
PY

rclone lsd "$remote:" --config "$temporary" --max-depth 1 >/dev/null
printf 'Confirm the authorization browser showed %s by typing CONNECT %s: ' \
    "$expected_email" "$expected_email"
IFS= read -r account_confirmation
if [ "$account_confirmation" != "CONNECT $expected_email" ]; then
    echo "Google account confirmation did not match; no token was installed." >&2
    exit 1
fi

install -o boxbrain -g boxbrain -m 0600 "$temporary" "$config"
for folder in Logs Config Projects Repositories Backups Media Diagnostics; do
    runuser -u boxbrain -- rclone mkdir "$remote:$folder" --config "$config"
done
runuser -u boxbrain -- rclone mkdir \
    "$remote:Repositories/Patches/inbox/$device_id" --config "$config"
runuser -u boxbrain -- rclone mkdir \
    "$remote:Repositories/Patches/receipts/$device_id" --config "$config"

set_environment() {
    name=$1
    value=$2
    if grep -q "^${name}=" "$environment"; then
        escaped=$(printf '%s' "$value" | sed 's/[\\&|]/\\&/g')
        sed -i "s|^${name}=.*|${name}=${escaped}|" "$environment"
    else
        printf '%s=%s\n' "$name" "$value" >>"$environment"
    fi
}

set_environment BOXBRAIN_DRIVE_DEVICE_ID "$device_id"
set_environment BOXBRAIN_DRIVE_REMOTE "$remote"
set_environment BOXBRAIN_DRIVE_CONFIG "$config"
set_environment BOXBRAIN_DRIVE_EXPECTED_ACCOUNT "$expected_email"

systemctl daemon-reload
systemctl enable --now boxbrain-drive-sync.timer
systemctl start boxbrain-drive-sync.service
systemctl is-active --quiet boxbrain-drive-sync.timer

trap - EXIT HUP INT TERM
rm -f "$temporary"
printf 'BoxBrain Drive transport is configured for %s and will run after reboot.\n' "$expected_email"
