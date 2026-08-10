#!/bin/sh
set -eu

gadget_root=/sys/kernel/config/usb_gadget
gadget="$gadget_root/boxbrain"
configuration="$gadget/configs/c.1"
keyboard_report_descriptor='\005\001\011\006\241\001\005\007\031\340\051\347\025\000\045\001\165\001\225\010\201\002\225\001\165\010\201\003\225\005\165\001\005\010\031\001\051\005\221\002\225\001\165\003\221\003\225\006\165\010\025\000\045\145\005\007\031\000\051\145\201\000\300'
mouse_report_descriptor='\005\001\011\002\241\001\011\001\241\000\005\011\031\001\051\003\025\000\045\001\165\001\225\003\201\002\165\005\225\001\201\001\005\001\011\060\011\061\011\070\025\201\045\177\165\010\225\003\201\006\300\300'
rescue_state_directory=${BOXBRAIN_STATE_DIR:-/var/lib/boxbrain}
rescue_image=''
rescue_write_mode='read-only'

require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "Run the BoxBrain USB gadget helper as root." >&2
        exit 1
    fi
}

cleanup_gadget() {
    if [ ! -d "$gadget" ]; then
        return
    fi
    if [ -e "$gadget/UDC" ]; then
        printf '' >"$gadget/UDC" || true
    fi
    if [ -e "$gadget/functions/mass_storage.rescue/lun.0/file" ]; then
        printf '' >"$gadget/functions/mass_storage.rescue/lun.0/file" || true
    fi
    rm -f \
        "$configuration/rndis.usb0" \
        "$configuration/hid.keyboard" \
        "$configuration/hid.mouse" \
        "$configuration/mass_storage.rescue" \
        "$gadget/os_desc/c.1"
    rmdir "$configuration/strings/0x409" 2>/dev/null || true
    rmdir "$configuration" 2>/dev/null || true
    rmdir "$gadget/functions/hid.mouse" 2>/dev/null || true
    rmdir "$gadget/functions/hid.keyboard" 2>/dev/null || true
    rmdir "$gadget/functions/rndis.usb0" 2>/dev/null || true
    rmdir "$gadget/functions/mass_storage.rescue" 2>/dev/null || true
    rmdir "$gadget/strings/0x409" 2>/dev/null || true
    rmdir "$gadget" 2>/dev/null || true
    if [ -d "$gadget" ]; then
        echo "The partial BoxBrain USB gadget could not be removed." >&2
        return 1
    fi
}

load_rescue_image() {
    rescue_plan=$(
        BOXBRAIN_STATE_DIR="$rescue_state_directory" \
        PYTHONPATH=/opt/boxbrain/src \
        python3 - <<'PY'
import os
from boxbrain.rescue_boot import RescueBootManager

manager = RescueBootManager(os.environ["BOXBRAIN_STATE_DIR"])
image = manager.active_image()
if image:
    print(f"{image['path']}|{image['write_mode']}")
PY
    )
    if [ -z "$rescue_plan" ]; then
        rescue_image=''
        rescue_write_mode='read-only'
        return
    fi
    rescue_image=${rescue_plan%%|*}
    rescue_write_mode=${rescue_plan#*|}
    if [ ! -f "$rescue_image" ]; then
        echo "The consumed rescue image is unavailable." >&2
        return 1
    fi
    case "$rescue_image" in
        "$rescue_state_directory"/rescue-images/*) ;;
        *)
            echo "Refusing to export anything outside the dedicated rescue image store." >&2
            return 1
            ;;
    esac
}

legacy_fallback() {
    cleanup_gadget || true
    modprobe g_ether || true
}

wait_for_endpoint() {
    attempt=0
    while [ "$attempt" -lt 50 ]; do
        if [ -d /sys/class/net/usb0 ] && [ -c /dev/hidg0 ] && [ -c /dev/hidg1 ]; then
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 0.1
    done
    return 1
}

start_gadget() {
    if [ -d "$gadget" ] && [ -s "$gadget/UDC" ]; then
        wait_for_endpoint
        return
    fi
    if [ -d /sys/module/g_ether ]; then
        echo "Legacy g_ether is active; reboot into the staged composite configuration." >&2
        return 1
    fi
    if ! mountpoint -q /sys/kernel/config; then
        echo "ConfigFS is not mounted at /sys/kernel/config." >&2
        return 1
    fi

    set -- /sys/class/udc/*
    if [ "$#" -ne 1 ] || [ ! -e "$1" ]; then
        echo "Exactly one USB device controller is required." >&2
        return 1
    fi
    udc=$(basename "$1")

    modprobe libcomposite
    modprobe usb_f_rndis
    modprobe usb_f_hid
    load_rescue_image
    if [ -n "$rescue_image" ]; then
        modprobe usb_f_mass_storage
    fi
    cleanup_gadget

    serial=$(tr -d '\000' </proc/device-tree/serial-number 2>/dev/null || true)
    serial=${serial:-boxbrain-pi}
    identity_hash=$(printf '%s' "$serial" | sha256sum | awk '{print $1}')
    dev_mac=$(printf '02:%s:%s:%s:%s:%s' \
        "$(printf '%s' "$identity_hash" | cut -c1-2)" \
        "$(printf '%s' "$identity_hash" | cut -c3-4)" \
        "$(printf '%s' "$identity_hash" | cut -c5-6)" \
        "$(printf '%s' "$identity_hash" | cut -c7-8)" \
        "$(printf '%s' "$identity_hash" | cut -c9-10)")
    host_mac=$(printf '06:%s:%s:%s:%s:%s' \
        "$(printf '%s' "$identity_hash" | cut -c11-12)" \
        "$(printf '%s' "$identity_hash" | cut -c13-14)" \
        "$(printf '%s' "$identity_hash" | cut -c15-16)" \
        "$(printf '%s' "$identity_hash" | cut -c17-18)" \
        "$(printf '%s' "$identity_hash" | cut -c19-20)")

    mkdir "$gadget"
    printf '0x2e8a' >"$gadget/idVendor"
    printf '0x0013' >"$gadget/idProduct"
    printf '0x0110' >"$gadget/bcdDevice"
    printf '0x0200' >"$gadget/bcdUSB"
    printf '0xef' >"$gadget/bDeviceClass"
    printf '0x02' >"$gadget/bDeviceSubClass"
    printf '0x01' >"$gadget/bDeviceProtocol"

    mkdir "$gadget/strings/0x409"
    printf '%s' "$serial" >"$gadget/strings/0x409/serialnumber"
    printf '%s' 'Raspberry Pi Ltd.' >"$gadget/strings/0x409/manufacturer"
    product='BoxBrain USB Ethernet + Keyboard + Mouse'
    configuration_label='BoxBrain RNDIS + HID Keyboard + Mouse'
    if [ -n "$rescue_image" ]; then
        product='BoxBrain One-Shot Rescue + Controls'
        configuration_label='BoxBrain Rescue Media + RNDIS + HID'
    fi
    printf '%s' "$product" >"$gadget/strings/0x409/product"

    mkdir "$configuration"
    mkdir "$configuration/strings/0x409"
    printf '%s' "$configuration_label" >"$configuration/strings/0x409/configuration"
    printf '250' >"$configuration/MaxPower"

    mkdir "$gadget/functions/rndis.usb0"
    printf 'usb%%d' >"$gadget/functions/rndis.usb0/ifname"
    printf '%s' "$dev_mac" >"$gadget/functions/rndis.usb0/dev_addr"
    printf '%s' "$host_mac" >"$gadget/functions/rndis.usb0/host_addr"

    printf '1' >"$gadget/os_desc/use"
    printf '0xcd' >"$gadget/os_desc/b_vendor_code"
    printf '%s' 'MSFT100' >"$gadget/os_desc/qw_sign"
    printf '%s' 'RNDIS' >\
        "$gadget/functions/rndis.usb0/os_desc/interface.rndis/compatible_id"
    printf '%s' '5162001' >\
        "$gadget/functions/rndis.usb0/os_desc/interface.rndis/sub_compatible_id"

    mkdir "$gadget/functions/hid.keyboard"
    printf '1' >"$gadget/functions/hid.keyboard/protocol"
    printf '1' >"$gadget/functions/hid.keyboard/subclass"
    printf '8' >"$gadget/functions/hid.keyboard/report_length"
    printf '%b' "$keyboard_report_descriptor" >"$gadget/functions/hid.keyboard/report_desc"

    mkdir "$gadget/functions/hid.mouse"
    printf '2' >"$gadget/functions/hid.mouse/protocol"
    printf '1' >"$gadget/functions/hid.mouse/subclass"
    printf '4' >"$gadget/functions/hid.mouse/report_length"
    printf '%b' "$mouse_report_descriptor" >"$gadget/functions/hid.mouse/report_desc"

    if [ -n "$rescue_image" ]; then
        mkdir "$gadget/functions/mass_storage.rescue"
        printf '1' >"$gadget/functions/mass_storage.rescue/stall"
        printf '1' >"$gadget/functions/mass_storage.rescue/lun.0/removable"
        if [ "$rescue_write_mode" = 'read-write' ]; then
            printf '0' >"$gadget/functions/mass_storage.rescue/lun.0/ro"
        else
            printf '1' >"$gadget/functions/mass_storage.rescue/lun.0/ro"
        fi
        case "$rescue_image" in
            *.iso) printf '1' >"$gadget/functions/mass_storage.rescue/lun.0/cdrom" ;;
            *) printf '0' >"$gadget/functions/mass_storage.rescue/lun.0/cdrom" ;;
        esac
        printf '%s' "$rescue_image" >"$gadget/functions/mass_storage.rescue/lun.0/file"
    fi

    ln -s "$gadget/functions/rndis.usb0" "$configuration/rndis.usb0"
    ln -s "$gadget/functions/hid.keyboard" "$configuration/hid.keyboard"
    ln -s "$gadget/functions/hid.mouse" "$configuration/hid.mouse"
    if [ -n "$rescue_image" ]; then
        ln -s "$gadget/functions/mass_storage.rescue" "$configuration/mass_storage.rescue"
    fi
    ln -s "$configuration" "$gadget/os_desc/c.1"
    printf '%s' "$udc" >"$gadget/UDC"

    if ! wait_for_endpoint; then
        echo "The composite gadget did not create usb0, /dev/hidg0, and /dev/hidg1." >&2
        legacy_fallback
        return 1
    fi
}

status_gadget() {
    active=false
    keyboard_ready=false
    mouse_ready=false
    ethernet_ready=false
    legacy=false
    [ ! -s "$gadget/UDC" ] || active=true
    [ ! -c /dev/hidg0 ] || keyboard_ready=true
    [ ! -c /dev/hidg1 ] || mouse_ready=true
    [ ! -d /sys/class/net/usb0 ] || ethernet_ready=true
    [ ! -d /sys/module/g_ether ] || legacy=true
    hid_ready=false
    if [ "$keyboard_ready" = true ] && [ "$mouse_ready" = true ]; then
        hid_ready=true
    fi
    printf '{"schema_version":1,"composite_active":%s,"hid_ready":%s,' \
        "$active" "$hid_ready"
    printf '"keyboard_ready":%s,"mouse_ready":%s,' \
        "$keyboard_ready" "$mouse_ready"
    printf '"ethernet_ready":%s,"legacy_g_ether_active":%s}\n' \
        "$ethernet_ready" "$legacy"
}

require_root
action=${1:-status}
case "$action" in
    start)
        if ! start_gadget; then
            legacy_fallback
            exit 1
        fi
        ;;
    stop)
        cleanup_gadget
        ;;
    rollback)
        cleanup_gadget
        modprobe g_ether
        ;;
    status)
        status_gadget
        ;;
    *)
        echo "Usage: boxbrain-usb-composite.sh {start|stop|rollback|status}" >&2
        exit 2
        ;;
esac
