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
    "Create the remote exactly as: $remote" \
    "Provider: Google Drive" \
    "Scope: drive" \
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

rclone config --config "$temporary"
redacted=$(rclone config redacted "$remote" --config "$temporary")
printf '%s\n' "$redacted" | grep -Eq '^type[[:space:]]*=[[:space:]]*drive$' || {
    echo "The $remote remote is missing or is not Google Drive." >&2
    exit 1
}
printf '%s\n' "$redacted" | grep -Eq '^scope[[:space:]]*=[[:space:]]*drive$' || {
    echo "The $remote remote must use the drive scope for operator-loaded patches." >&2
    exit 1
}
configured_root=$(
    printf '%s\n' "$redacted" |
        sed -n 's/^root_folder_id[[:space:]]*=[[:space:]]*//p' |
        tail -n 1
)
if [ "$configured_root" != "$root_folder_id" ]; then
    echo "The configured Drive root does not match ROOT_FOLDER_ID." >&2
    exit 1
fi

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
