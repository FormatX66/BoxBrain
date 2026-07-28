#!/bin/sh
set -eu
umask 077

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this upgrade with sudo." >&2
    exit 1
fi

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
target_version=$(sed -n '1p' "$project_dir/VERSION")
case "$target_version" in
    ''|*[!0-9A-Za-z.-]*)
        echo "The target VERSION is invalid." >&2
        exit 1
        ;;
esac

if [ ! -s /opt/boxbrain/VERSION ]; then
    echo "BoxBrain is not installed. Run scripts/install.sh first." >&2
    exit 1
fi

backup_directory=/var/backups/boxbrain
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
backup="$backup_directory/pre-$target_version-$timestamp.tar.gz"
install -d -o root -g root -m 0700 "$backup_directory"
test ! -e "$backup"

restart_services() {
    systemctl daemon-reload
    systemctl restart \
        boxbrain.service \
        boxbrain-onboarding.service \
        boxbrain-link-monitor.service
}

if ! systemctl stop \
    boxbrain-link-monitor.service \
    boxbrain-onboarding.service \
    boxbrain.service; then
    restart_services
    echo "Could not stop every BoxBrain service; the services were restarted." >&2
    exit 1
fi

if ! (
    tar -czf "$backup" \
        /opt/boxbrain \
        /etc/boxbrain \
        /var/lib/boxbrain \
        /etc/systemd/system/boxbrain.service \
        /etc/systemd/system/boxbrain-onboarding.service \
        /etc/systemd/system/boxbrain-link-monitor.service \
        /usr/local/bin/boxbrainctl &&
        chmod 0600 "$backup" &&
        tar -tzf "$backup" >/dev/null
); then
    rm -f "$backup"
    restart_services
    echo "Backup failed; the existing services were restarted." >&2
    exit 1
fi

rollback() {
    code=$1
    if [ "$code" -eq 0 ]; then
        return
    fi
    trap - EXIT
    echo "Upgrade failed; restoring $backup" >&2
    rm -rf /opt/boxbrain
    tar -xzf "$backup" -C /
    restart_services
    systemctl is-active --quiet boxbrain.service
    systemctl is-active --quiet boxbrain-onboarding.service
    systemctl is-active --quiet boxbrain-link-monitor.service
    exit "$code"
}
trap 'rollback $?' EXIT

sh "$project_dir/scripts/install.sh"

test "$(cat /opt/boxbrain/VERSION)" = "$target_version"
systemctl is-active --quiet boxbrain.service
systemctl is-active --quiet boxbrain-onboarding.service
systemctl is-active --quiet boxbrain-link-monitor.service
/usr/local/bin/boxbrainctl health >/dev/null
/usr/local/bin/boxbrainctl agent >/dev/null
/usr/local/bin/boxbrainctl targets >/dev/null

onboarding_bind=$(
    sed -n 's/^BOXBRAIN_ONBOARDING_BIND=//p' /etc/boxbrain/boxbrain.env |
        tail -n 1
)
onboarding_port=$(
    sed -n 's/^BOXBRAIN_ONBOARDING_PORT=//p' /etc/boxbrain/boxbrain.env |
        tail -n 1
)
onboarding_bind=${onboarding_bind:-10.12.194.1}
onboarding_port=${onboarding_port:-8788}
python3 - "$onboarding_bind" "$onboarding_port" <<'PY'
import json
import sys
from urllib.request import ProxyHandler, build_opener

host, port = sys.argv[1:]
opener = build_opener(ProxyHandler({}))
with opener.open(f"http://{host}:{port}/health", timeout=5) as response:
    payload = json.load(response)
if payload.get("status") != "ok":
    raise SystemExit("Onboarding health check failed.")
PY

trap - EXIT
printf 'BoxBrain %s upgraded and verified.\n' "$target_version"
printf 'Rollback archive: %s\n' "$backup"
