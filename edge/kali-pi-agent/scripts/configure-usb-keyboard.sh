#!/bin/sh
set -eu
umask 077

state_dir=/var/lib/boxbrain/usb-gadget
legacy_modules=/etc/modules-load.d/usb-gadget.conf
composite_modules=/etc/modules-load.d/boxbrain-composite-gadget.conf
marker=/etc/boxbrain/usb-keyboard-enabled
pending="$state_dir/pending"
backup="$state_dir/usb-gadget.conf.legacy"
backup_absent="$state_dir/usb-gadget.conf.was-absent"
composite_helper=/usr/local/libexec/boxbrain-usb-composite
gadget_service=boxbrain-usb-gadget.service
rollback_timer=boxbrain-usb-gadget-rollback.timer

require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "Run USB HID configuration with sudo." >&2
        exit 1
    fi
}

preview() {
    staged=false
    pending_state=false
    service_enabled=false
    service_active=false
    keyboard_ready=false
    mouse_ready=false
    ethernet_ready=false
    legacy_active=false
    [ ! -e "$marker" ] || staged=true
    [ ! -e "$pending" ] || pending_state=true
    systemctl is-enabled --quiet "$gadget_service" 2>/dev/null && service_enabled=true || true
    systemctl is-active --quiet "$gadget_service" 2>/dev/null && service_active=true || true
    [ ! -c /dev/hidg0 ] || keyboard_ready=true
    [ ! -c /dev/hidg1 ] || mouse_ready=true
    [ ! -d /sys/class/net/usb0 ] || ethernet_ready=true
    [ ! -d /sys/module/g_ether ] || legacy_active=true
    requires_reboot=false
    if [ "$staged" = true ] && [ "$service_active" = false ]; then
        requires_reboot=true
    fi
    printf '{"schema_version":1,"action":"preview","changed":false,'
    printf '"staged":%s,"pending_commit":%s,' "$staged" "$pending_state"
    printf '"service_enabled":%s,"service_active":%s,' \
        "$service_enabled" "$service_active"
    hid_ready=false
    if [ "$keyboard_ready" = true ] && [ "$mouse_ready" = true ]; then
        hid_ready=true
    fi
    printf '"hid_ready":%s,"keyboard_ready":%s,"mouse_ready":%s,' \
        "$hid_ready" "$keyboard_ready" "$mouse_ready"
    printf '"ethernet_ready":%s,' "$ethernet_ready"
    printf '"legacy_g_ether_active":%s,' "$legacy_active"
    printf '"requires_reboot_to_activate":%s}\n' "$requires_reboot"
}

validate_interface() {
    interface=$1
    if ! printf '%s\n' "$interface" | grep -Eq '^[A-Za-z0-9_.:-]{1,32}$'; then
        echo "The alternate management interface is invalid." >&2
        exit 1
    fi
    if [ "$interface" = usb0 ] || [ ! -d "/sys/class/net/$interface" ]; then
        echo "A non-USB alternate management interface is required." >&2
        exit 1
    fi
    if ! ip -4 -o address show dev "$interface" scope global | grep -q ' inet '; then
        echo "The alternate management interface has no global IPv4 address." >&2
        exit 1
    fi
}

require_approval() {
    expected=$1
    authorized=$2
    confirmation=$3
    if [ "$authorized" != true ]; then
        echo "Explicit USB HID authorization is required." >&2
        exit 1
    fi
    if [ "$confirmation" != "$expected" ]; then
        echo "Exact confirmation required: $expected" >&2
        exit 1
    fi
}

restore_modules() {
    rm -f "$composite_modules"
    if [ -f "$backup" ]; then
        install -o root -g root -m 0644 "$backup" "$legacy_modules"
    elif [ -e "$backup_absent" ]; then
        rm -f "$legacy_modules"
    else
        printf '%s\n' g_ether >"$legacy_modules"
        chown root:root "$legacy_modules"
        chmod 0644 "$legacy_modules"
    fi
}

rollback_internal() {
    systemctl disable "$rollback_timer" >/dev/null 2>&1 || true
    systemctl stop "$rollback_timer" >/dev/null 2>&1 || true
    if systemctl is-active --quiet "$gadget_service" 2>/dev/null; then
        systemctl stop "$gadget_service" || true
    elif [ -d /sys/kernel/config/usb_gadget/boxbrain ]; then
        "$composite_helper" stop || true
    fi
    systemctl disable "$gadget_service" >/dev/null 2>&1 || true
    rm -f "$marker" "$pending"
    restore_modules
    modprobe g_ether
    systemctl daemon-reload
}

action=${1:-preview}
shift || true
authorized=false
confirmation=
alternate_interface=wlan0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --authorized)
            authorized=true
            ;;
        --confirmation)
            [ "$#" -ge 2 ] || { echo "--confirmation requires a value." >&2; exit 2; }
            confirmation=$2
            shift
            ;;
        --alternate-interface)
            [ "$#" -ge 2 ] || { echo "--alternate-interface requires a value." >&2; exit 2; }
            alternate_interface=$2
            shift
            ;;
        *)
            echo "Unsupported USB HID option: $1" >&2
            exit 2
            ;;
    esac
    shift
done

case "$action" in
    preview)
        require_root
        preview
        ;;
    stage)
        require_root
        require_approval 'STAGE USB HID' "$authorized" "$confirmation"
        validate_interface "$alternate_interface"
        if systemctl is-active --quiet "$gadget_service" 2>/dev/null; then
            echo "The composite gadget is already active." >&2
            exit 1
        fi
        install -d -o root -g root -m 0700 "$state_dir"
        if [ ! -e "$backup" ] && [ ! -e "$backup_absent" ]; then
            if [ -f "$legacy_modules" ]; then
                install -o root -g root -m 0600 "$legacy_modules" "$backup"
            else
                : >"$backup_absent"
            fi
        fi
        temporary="$state_dir/modules.tmp"
        if [ -f "$legacy_modules" ]; then
            sed '/^[[:space:]]*g_ether[[:space:]]*$/d' "$legacy_modules" >"$temporary"
            install -o root -g root -m 0644 "$temporary" "$legacy_modules"
        fi
        printf '%s\n' libcomposite usb_f_rndis usb_f_hid >"$temporary"
        install -o root -g root -m 0644 "$temporary" "$composite_modules"
        rm -f "$temporary"
        : >"$marker"
        printf '%s\n' "$alternate_interface" >"$pending"
        chmod 0600 "$pending"
        systemctl daemon-reload
        if ! systemctl enable "$gadget_service" "$rollback_timer" >/dev/null; then
            rm -f "$marker" "$pending"
            restore_modules
            systemctl daemon-reload
            exit 1
        fi
        printf '{"schema_version":1,"action":"stage","changed":true,'
        printf '"reboot_required":true,"rollback_deadline_minutes":15,'
        printf '"alternate_interface":"%s"}\n' "$alternate_interface"
        ;;
    commit)
        require_root
        require_approval 'COMMIT USB HID' "$authorized" "$confirmation"
        [ -e "$pending" ] || { echo "No USB HID migration is pending." >&2; exit 1; }
        systemctl is-active --quiet "$gadget_service"
        [ -c /dev/hidg0 ]
        [ -c /dev/hidg1 ]
        [ -d /sys/class/net/usb0 ]
        [ ! -d /sys/module/g_ether ]
        [ -s /sys/kernel/config/usb_gadget/boxbrain/UDC ]
        systemctl disable --now "$rollback_timer" >/dev/null
        rm -f "$pending"
        printf '%s\n' '{"schema_version":1,"action":"commit","changed":true,"status":"persistent"}'
        ;;
    rollback)
        require_root
        require_approval 'ROLL BACK USB HID' "$authorized" "$confirmation"
        rollback_internal
        printf '%s\n' '{"schema_version":1,"action":"rollback","changed":true,"status":"legacy_g_ether_restored"}'
        ;;
    rollback-pending)
        require_root
        if [ -e "$pending" ]; then
            logger -t boxbrain-usb-gadget 'Pending composite gadget was not committed; restoring g_ether.'
            rollback_internal
        fi
        ;;
    *)
        echo "Usage: configure-usb-keyboard.sh {preview|stage|commit|rollback}" >&2
        exit 2
        ;;
esac
