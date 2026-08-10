#!/bin/sh
set -eu
umask 077

credential_dir=/etc/boxbrain/access-point
state_dir=/var/lib/boxbrain/access-point
pending="$state_dir/pending"
helper=/usr/local/libexec/boxbrain-access-point
service=boxbrain-access-point.service
rollback_timer=boxbrain-access-point-rollback.timer
network_mode_service=boxbrain-network-mode.service
network_mode_timer=boxbrain-network-mode.timer

require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "Run access-point configuration with sudo." >&2
        exit 1
    fi
}

require_approval() {
    expected=$1
    if [ "$authorized" != true ]; then
        echo "Explicit access-point authorization is required." >&2
        exit 1
    fi
    if [ "$confirmation" != "$expected" ]; then
        echo "Exact confirmation required: $expected" >&2
        exit 1
    fi
}

create_credentials() {
    install -d -o root -g root -m 0700 "$credential_dir"
    if [ ! -s "$credential_dir/ssid" ]; then
        serial=$(tr -d '\000' </proc/device-tree/serial-number 2>/dev/null || true)
        serial=${serial:-boxbrainpi}
        suffix=$(printf '%s' "$serial" | sha256sum | cut -c1-8)
        printf 'BoxBrain-%s\n' "$suffix" >"$credential_dir/ssid"
    fi
    if [ ! -s "$credential_dir/psk" ]; then
        key=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n' | sha256sum | cut -c1-24)
        printf '%s\n' "$key" >"$credential_dir/psk"
    fi
    if [ ! -s "$credential_dir/uuid" ]; then
        cat /proc/sys/kernel/random/uuid >"$credential_dir/uuid"
    fi
    chown root:root "$credential_dir"/*
    chmod 0600 "$credential_dir"/*
}

preview() {
    configured=false
    pending_state=false
    service_enabled=false
    service_active=false
    [ ! -s "$credential_dir/ssid" ] || configured=true
    [ ! -e "$pending" ] || pending_state=true
    systemctl is-enabled --quiet "$service" 2>/dev/null && service_enabled=true || true
    systemctl is-active --quiet "$service" 2>/dev/null && service_active=true || true
    printf '{"schema_version":1,"action":"preview","changed":false,'
    printf '"configured":%s,"pending_commit":%s,' "$configured" "$pending_state"
    printf '"service_enabled":%s,"service_active":%s,' \
        "$service_enabled" "$service_active"
    if [ -x "$helper" ]; then
        "$helper" status | sed 's/^{/"runtime":{/' | sed 's/}$/}}/'
    else
        printf '"runtime":null}\n'
    fi
}

rollback_internal() {
    systemctl disable --now "$rollback_timer" >/dev/null 2>&1 || true
    systemctl disable --now "$service" >/dev/null 2>&1 || true
    rm -f "$pending"
}

action=${1:-preview}
shift || true
authorized=false
confirmation=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --authorized) authorized=true ;;
        --confirmation)
            [ "$#" -ge 2 ] || { echo "--confirmation requires a value." >&2; exit 2; }
            confirmation=$2
            shift
            ;;
        *) echo "Unsupported access-point option: $1" >&2; exit 2 ;;
    esac
    shift
done

require_root
case "$action" in
    preview)
        preview
        ;;
    stage)
        require_approval 'STAGE ACCESS POINT'
        create_credentials
        install -d -o root -g root -m 0700 "$state_dir"
        : >"$pending"
        systemctl daemon-reload
        systemctl enable "$service" "$rollback_timer" >/dev/null
        if ! systemctl start "$service"; then
            rollback_internal
            exit 1
        fi
        systemctl start "$rollback_timer"
        ssid=$(sed -n '1p' "$credential_dir/ssid")
        printf '{"schema_version":1,"action":"stage","changed":true,'
        printf '"ssid":"%s","address":"10.42.194.1",' "$ssid"
        printf '"rollback_deadline_minutes":15}\n'
        ;;
    commit)
        require_approval 'COMMIT ACCESS POINT'
        [ -e "$pending" ] || { echo "No access-point migration is pending." >&2; exit 1; }
        systemctl is-active --quiet "$service"
        "$helper" status | grep -q '"active":true'
        "$helper" status | grep -q '"address_ready":true'
        "$helper" status | grep -q '"isolated":true'
        systemctl disable --now "$rollback_timer" >/dev/null
        rm -f "$pending"
        systemctl disable "$service" >/dev/null 2>&1 || true
        systemctl enable --now "$network_mode_timer" >/dev/null
        systemctl start "$network_mode_service" || true
        printf '%s\n' '{"schema_version":1,"action":"commit","changed":true,"status":"persistent"}'
        ;;
    rollback)
        require_approval 'ROLL BACK ACCESS POINT'
        rollback_internal
        printf '%s\n' '{"schema_version":1,"action":"rollback","changed":true,"status":"disabled"}'
        ;;
    rollback-pending)
        if [ -e "$pending" ]; then
            logger -t boxbrain-access-point 'Pending access point was not committed; disabling it.'
            rollback_internal
        fi
        ;;
    *)
        echo "Usage: configure-access-point.sh {preview|stage|commit|rollback}" >&2
        exit 2
        ;;
esac
