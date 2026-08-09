#!/bin/sh
set -eu

export LC_ALL=C

wifi_interface=${BOXBRAIN_LOCAL_WIFI_INTERFACE:-wlan0}
usb_interface=${BOXBRAIN_TARGET_USB_INTERFACE:-usb0}
ethernet_interface=${BOXBRAIN_TARGET_ETHERNET_INTERFACE:-eth0}
ap_interface=${BOXBRAIN_AP_INTERFACE:-bbap0}
target_address=${BOXBRAIN_TARGET_ETHERNET_ADDRESS:-10.12.194.1}
ap_service=${BOXBRAIN_AP_SERVICE:-boxbrain-access-point.service}
state_dir=/run/boxbrain
state_file="$state_dir/network-mode"

require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "Run the BoxBrain network-mode helper as root." >&2
        exit 1
    fi
}

carrier_is_up() {
    interface=$1
    carrier="/sys/class/net/$interface/carrier"
    [ -r "$carrier" ] && [ "$(cat "$carrier" 2>/dev/null || true)" = 1 ]
}

target_ethernet_is_up() {
    carrier_is_up "$ethernet_interface" || return 1
    ip -4 -o address show dev "$ethernet_interface" 2>/dev/null |
        grep -Fq " $target_address/"
}

ap_has_client() {
    [ -d "/sys/class/net/$ap_interface" ] || return 1
    iw dev "$ap_interface" station dump 2>/dev/null |
        grep -q '^Station '
}

target_is_attached() {
    [ -e /var/lib/boxbrain/access-point/pending ] ||
        carrier_is_up "$usb_interface" ||
        target_ethernet_is_up ||
        ap_has_client
}

local_wifi_is_connected() {
    nmcli -t -f DEVICE,TYPE,STATE device status 2>/dev/null |
        grep -Fxq "$wifi_interface:wifi:connected"
}

write_mode() {
    mode=$1
    install -d -o root -g root -m 0755 "$state_dir"
    previous=$(sed -n '1p' "$state_file" 2>/dev/null || true)
    if [ "$previous" != "$mode" ]; then
        printf '%s\n' "$mode" >"$state_file"
        logger -t boxbrain-network-mode "network mode changed: ${previous:-unknown} -> $mode"
    fi
    printf '%s\n' "$mode"
}

activate_target_mode() {
    if [ -s /etc/boxbrain/access-point/psk ]; then
        systemctl start "$ap_service"
        write_mode target
    else
        write_mode target-no-ap
    fi
}

activate_standalone_mode() {
    systemctl stop "$ap_service" >/dev/null 2>&1 || true
    nmcli device set "$wifi_interface" managed yes
    if ! local_wifi_is_connected; then
        nmcli device connect "$wifi_interface" >/dev/null || return 1
    fi
    local_wifi_is_connected || return 1
    write_mode standalone-local
}

status_mode() {
    target=false
    local_wifi=false
    ap_client=false
    target_is_attached && target=true || true
    local_wifi_is_connected && local_wifi=true || true
    ap_has_client && ap_client=true || true
    mode=$(sed -n '1p' "$state_file" 2>/dev/null || true)
    printf '{"schema_version":1,"mode":"%s",' "${mode:-unknown}"
    printf '"target_attached":%s,"local_wifi_connected":%s,' "$target" "$local_wifi"
    printf '"ap_client_connected":%s}\n' "$ap_client"
}

require_root
action=${1:-reconcile}
case "$action" in
    reconcile)
        command -v ip >/dev/null
        command -v iw >/dev/null
        command -v nmcli >/dev/null
        if target_is_attached; then
            activate_target_mode
        elif ! activate_standalone_mode; then
            write_mode standalone-no-uplink
            echo "No saved local Wi-Fi profile is currently reachable; the timer will retry." >&2
            exit 1
        fi
        ;;
    status)
        status_mode
        ;;
    *)
        echo "Usage: boxbrain-network-mode {reconcile|status}" >&2
        exit 2
        ;;
esac
