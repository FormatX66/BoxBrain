#!/bin/sh
set -eu

physical_interface=${BOXBRAIN_AP_PHYSICAL_INTERFACE:-wlan0}
ap_interface=${BOXBRAIN_AP_INTERFACE:-bbap0}
connection_id=${BOXBRAIN_AP_CONNECTION_ID:-BoxBrain-AP}
address=${BOXBRAIN_AP_ADDRESS:-10.42.194.1/24}
credential_dir=/etc/boxbrain/access-point
ssid_file="$credential_dir/ssid"
psk_file="$credential_dir/psk"
uuid_file="$credential_dir/uuid"
keyfile=/etc/NetworkManager/system-connections/boxbrain-ap.nmconnection
nft_table=boxbrain_ap

require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "Run the BoxBrain access-point helper as root." >&2
        exit 1
    fi
}

read_value() {
    file=$1
    [ -f "$file" ] || return 1
    sed -n '1p' "$file"
}

validate_configuration() {
    ssid=$(read_value "$ssid_file") || {
        echo "The BoxBrain access-point SSID is not configured." >&2
        return 1
    }
    psk=$(read_value "$psk_file") || {
        echo "The BoxBrain access-point key is not configured." >&2
        return 1
    }
    uuid=$(read_value "$uuid_file") || {
        echo "The BoxBrain access-point UUID is not configured." >&2
        return 1
    }
    printf '%s\n' "$ssid" | grep -Eq '^[A-Za-z0-9._-]{1,32}$' || {
        echo "The BoxBrain access-point SSID is invalid." >&2
        return 1
    }
    printf '%s\n' "$psk" | grep -Eq '^[A-Za-z0-9._-]{12,63}$' || {
        echo "The BoxBrain access-point key is invalid." >&2
        return 1
    }
    printf '%s\n' "$uuid" | grep -Eq \
        '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' || {
        echo "The BoxBrain access-point UUID is invalid." >&2
        return 1
    }
    for interface in "$physical_interface" "$ap_interface"; do
        printf '%s\n' "$interface" | grep -Eq '^[A-Za-z0-9_.:-]{1,32}$' || {
            echo "The BoxBrain access-point interface is invalid." >&2
            return 1
        }
    done
    [ -d "/sys/class/net/$physical_interface" ] || {
        echo "The physical Wi-Fi interface is unavailable." >&2
        return 1
    }
}

current_channel() {
    channel=$(iw dev "$physical_interface" info 2>/dev/null |
        awk '/channel [0-9]+/ {print $2; exit}')
    if [ -z "$channel" ]; then
        channel=$(iw dev "$physical_interface" link 2>/dev/null |
            awk '/freq:/ {
                if ($2 == 2484) print 14;
                else if ($2 >= 2412 && $2 <= 2472) print int(($2 - 2407) / 5);
                else if ($2 >= 5000 && $2 <= 5900) print int(($2 - 5000) / 5);
                exit
            }')
    fi
    channel=${channel:-6}
    printf '%s\n' "$channel"
}

channel_band() {
    if [ "$1" -le 14 ]; then
        printf '%s\n' bg
    else
        printf '%s\n' a
    fi
}

write_keyfile() {
    channel=$1
    band=$(channel_band "$channel")
    temporary="$credential_dir/boxbrain-ap.nmconnection.tmp"
    {
        printf '%s\n' '[connection]'
        printf 'id=%s\n' "$connection_id"
        printf 'uuid=%s\n' "$uuid"
        printf '%s\n' 'type=wifi' 'interface-name='"$ap_interface" 'autoconnect=false'
        printf '\n%s\n' '[wifi]'
        printf 'band=%s\nchannel=%s\nmode=ap\nssid=%s\n' "$band" "$channel" "$ssid"
        printf '\n%s\n' '[wifi-security]'
        printf 'group=ccmp;\nkey-mgmt=wpa-psk\npairwise=ccmp;\nproto=rsn;\npsk=%s\n' "$psk"
        printf '\n%s\n' '[ipv4]'
        printf 'address1=%s\nmethod=shared\nnever-default=true\n' "$address"
        printf '\n%s\n' '[ipv6]' 'method=disabled'
    } >"$temporary"
    install -o root -g root -m 0600 "$temporary" "$keyfile"
    rm -f "$temporary"
}

remove_isolation() {
    nft delete table inet "$nft_table" >/dev/null 2>&1 || true
}

apply_isolation() {
    remove_isolation
    nft add table inet "$nft_table"
    nft 'add chain inet boxbrain_ap forward { type filter hook forward priority 10; policy accept; }'
    nft add rule inet "$nft_table" forward \
        iifname "$ap_interface" oifname != "$ap_interface" reject
}

cleanup_runtime() {
    remove_isolation
    nmcli connection down uuid "$uuid" >/dev/null 2>&1 || true
    if iw dev "$ap_interface" info >/dev/null 2>&1; then
        iw dev "$ap_interface" del >/dev/null 2>&1 || true
    fi
}

start_access_point() {
    validate_configuration
    command -v nmcli >/dev/null
    command -v iw >/dev/null
    command -v nft >/dev/null

    channel=$(current_channel)
    if ! iw dev "$ap_interface" info >/dev/null 2>&1; then
        iw dev "$physical_interface" interface add "$ap_interface" type __ap
    fi
    attempt=0
    until nmcli -t -f DEVICE device status | grep -Fxq "$ap_interface"; do
        attempt=$((attempt + 1))
        if [ "$attempt" -ge 25 ]; then
            echo "NetworkManager did not discover the access-point interface." >&2
            return 1
        fi
        sleep 0.2
    done
    nmcli device set "$ap_interface" managed yes
    write_keyfile "$channel"
    nmcli connection reload
    nmcli connection up uuid "$uuid" ifname "$ap_interface"
    apply_isolation

    ip -4 -o address show dev "$ap_interface" | grep -Fq " $address"
}

status_access_point() {
    active=false
    interface_ready=false
    address_ready=false
    isolated=false
    configured=false
    ssid=""
    [ ! -f "$ssid_file" ] || {
        configured=true
        ssid=$(read_value "$ssid_file")
    }
    [ ! -d "/sys/class/net/$ap_interface" ] || interface_ready=true
    if nmcli -t -f UUID,DEVICE connection show --active 2>/dev/null |
        grep -Fq "$uuid:$ap_interface"; then
        active=true
    fi
    if ip -4 -o address show dev "$ap_interface" 2>/dev/null |
        grep -Fq " $address"; then
        address_ready=true
    fi
    nft list table inet "$nft_table" >/dev/null 2>&1 && isolated=true || true
    printf '{"schema_version":1,"configured":%s,"active":%s,' \
        "$configured" "$active"
    printf '"interface_ready":%s,"address_ready":%s,' \
        "$interface_ready" "$address_ready"
    printf '"isolated":%s,"interface":"%s","address":"%s","ssid":"%s"}\n' \
        "$isolated" "$ap_interface" "$address" "$ssid"
}

require_root
action=${1:-status}
case "$action" in
    start)
        if ! start_access_point; then
            cleanup_runtime
            echo "The BoxBrain access point failed to start; existing links were preserved." >&2
            exit 1
        fi
        ;;
    stop)
        if [ -f "$uuid_file" ]; then
            uuid=$(read_value "$uuid_file")
            cleanup_runtime
        else
            remove_isolation
        fi
        ;;
    status)
        uuid=$(read_value "$uuid_file" 2>/dev/null || true)
        status_access_point
        ;;
    *)
        echo "Usage: boxbrain-access-point.sh {start|stop|status}" >&2
        exit 2
        ;;
esac
