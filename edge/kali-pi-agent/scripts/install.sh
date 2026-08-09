#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer with sudo." >&2
    exit 1
fi

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

if ! getent group boxbrain >/dev/null 2>&1; then
    groupadd --system boxbrain
fi

if ! getent passwd boxbrain >/dev/null 2>&1; then
    useradd \
        --system \
        --gid boxbrain \
        --home-dir /var/lib/boxbrain \
        --shell /usr/sbin/nologin \
        boxbrain
fi

if id kali >/dev/null 2>&1; then
    usermod -a -G boxbrain kali
fi

install -d -o root -g root -m 0755 /opt/boxbrain/src/boxbrain
install -d -o root -g root -m 0755 /opt/boxbrain/onboarding
install -d -o root -g boxbrain -m 0750 /etc/boxbrain
install -d -o boxbrain -g boxbrain -m 0750 /var/lib/boxbrain
install -d -o boxbrain -g boxbrain -m 0700 /var/lib/boxbrain/identity
install -d -o boxbrain -g boxbrain -m 0750 /var/lib/boxbrain/links
install -d -o boxbrain -g boxbrain -m 0700 /var/lib/boxbrain/logs
install -d -o boxbrain -g boxbrain -m 0700 /var/lib/boxbrain/drive/patches/inbox
install -d -o boxbrain -g boxbrain -m 0700 /var/lib/boxbrain/drive/patches/verified
install -d -o boxbrain -g boxbrain -m 0700 /var/lib/boxbrain/drive/patches/receipts
install -d -o root -g root -m 0700 /var/lib/boxbrain/usb-gadget
install -d -o root -g boxbrain -m 0750 /var/lib/boxbrain/hid-kvm
install -d -o boxbrain -g boxbrain -m 0750 /var/lib/boxbrain/rescue
install -d -o boxbrain -g boxbrain -m 0750 /var/lib/boxbrain/rescue/backups
install -d -o boxbrain -g boxbrain -m 0750 /var/lib/boxbrain/rescue-images
install -d -o root -g root -m 0755 /usr/local/libexec
install -d -o root -g root -m 0755 /usr/local/sbin

if [ ! -s /var/lib/boxbrain/identity/target_ed25519 ]; then
    runuser -u boxbrain -- ssh-keygen \
        -q \
        -t ed25519 \
        -N '' \
        -C boxbrain-target-access \
        -f /var/lib/boxbrain/identity/target_ed25519
fi
chmod 0600 /var/lib/boxbrain/identity/target_ed25519
chmod 0644 /var/lib/boxbrain/identity/target_ed25519.pub
public_key=$(cat /var/lib/boxbrain/identity/target_ed25519.pub)

install -o root -g root -m 0644 "$project_dir"/README.md /opt/boxbrain/README.md
install -o root -g root -m 0644 "$project_dir"/VERSION /opt/boxbrain/VERSION
install -o root -g root -m 0644 "$project_dir"/src/boxbrain/*.py /opt/boxbrain/src/boxbrain/
sed "s|__BOXBRAIN_PUBLIC_KEY__|$public_key|g" \
    "$project_dir"/onboarding/windows-link.ps1 \
    >/opt/boxbrain/onboarding/windows-link.ps1
sed "s|__BOXBRAIN_PUBLIC_KEY__|$public_key|g" \
    "$project_dir"/onboarding/linux-link.sh \
    >/opt/boxbrain/onboarding/linux-link.sh
install -o root -g root -m 0644 \
    "$project_dir"/onboarding/windows-wifi-provision.ps1 \
    /opt/boxbrain/onboarding/windows-wifi-provision.ps1
install -o root -g root -m 0644 \
    /var/lib/boxbrain/identity/target_ed25519.pub \
    /opt/boxbrain/onboarding/boxbrain-target.pub
chown root:root \
    /opt/boxbrain/onboarding/windows-link.ps1 \
    /opt/boxbrain/onboarding/windows-wifi-provision.ps1 \
    /opt/boxbrain/onboarding/linux-link.sh
chmod 0644 \
    /opt/boxbrain/onboarding/windows-link.ps1 \
    /opt/boxbrain/onboarding/windows-wifi-provision.ps1 \
    /opt/boxbrain/onboarding/linux-link.sh
install -o root -g root -m 0755 "$project_dir"/scripts/boxbrainctl /usr/local/bin/boxbrainctl
install -o root -g root -m 0755 \
    "$project_dir"/scripts/configure-drive.sh \
    /usr/local/bin/boxbrain-drive-configure
install -o root -g root -m 0755 \
    "$project_dir"/scripts/boxbrain-usb-composite.sh \
    /usr/local/libexec/boxbrain-usb-composite
install -o root -g root -m 0755 \
    "$project_dir"/scripts/boxbrain-access-point.sh \
    /usr/local/libexec/boxbrain-access-point
install -o root -g root -m 0755 \
    "$project_dir"/scripts/configure-usb-keyboard.sh \
    /usr/local/sbin/boxbrain-usb-keyboard-config
install -o root -g root -m 0755 \
    "$project_dir"/scripts/configure-access-point.sh \
    /usr/local/sbin/boxbrain-access-point-config
install -o root -g root -m 0644 "$project_dir"/systemd/boxbrain.service /etc/systemd/system/boxbrain.service
install -o root -g root -m 0644 "$project_dir"/systemd/boxbrain-onboarding.service /etc/systemd/system/boxbrain-onboarding.service
install -o root -g root -m 0644 "$project_dir"/systemd/boxbrain-link-monitor.service /etc/systemd/system/boxbrain-link-monitor.service
install -o root -g root -m 0644 \
    "$project_dir"/systemd/boxbrain-drive-sync.service \
    /etc/systemd/system/boxbrain-drive-sync.service
install -o root -g root -m 0644 \
    "$project_dir"/systemd/boxbrain-drive-sync.timer \
    /etc/systemd/system/boxbrain-drive-sync.timer
install -o root -g root -m 0644 \
    "$project_dir"/systemd/boxbrain-usb-gadget.service \
    /etc/systemd/system/boxbrain-usb-gadget.service
install -o root -g root -m 0644 \
    "$project_dir"/systemd/boxbrain-rescue-early.service \
    /etc/systemd/system/boxbrain-rescue-early.service
install -o root -g root -m 0644 \
    "$project_dir"/systemd/boxbrain-usb-gadget-rollback.service \
    /etc/systemd/system/boxbrain-usb-gadget-rollback.service
install -o root -g root -m 0644 \
    "$project_dir"/systemd/boxbrain-usb-gadget-rollback.timer \
    /etc/systemd/system/boxbrain-usb-gadget-rollback.timer
install -o root -g root -m 0644 \
    "$project_dir"/systemd/boxbrain-hid-kvm.service \
    /etc/systemd/system/boxbrain-hid-kvm.service
install -o root -g root -m 0644 \
    "$project_dir"/systemd/boxbrain-access-point.service \
    /etc/systemd/system/boxbrain-access-point.service
install -o root -g root -m 0644 \
    "$project_dir"/systemd/boxbrain-access-point-rollback.service \
    /etc/systemd/system/boxbrain-access-point-rollback.service
install -o root -g root -m 0644 \
    "$project_dir"/systemd/boxbrain-access-point-rollback.timer \
    /etc/systemd/system/boxbrain-access-point-rollback.timer

if [ ! -e /etc/boxbrain/boxbrain.env ]; then
    install -o root -g boxbrain -m 0640 "$project_dir"/config/boxbrain.env /etc/boxbrain/boxbrain.env
fi

ensure_env_setting() {
    setting_name=$1
    setting_value=$2
    if ! grep -q "^${setting_name}=" /etc/boxbrain/boxbrain.env; then
        printf '%s=%s\n' "$setting_name" "$setting_value" >>/etc/boxbrain/boxbrain.env
    fi
}

ensure_env_setting BOXBRAIN_DIAGNOSTIC_INTERVAL 900
ensure_env_setting BOXBRAIN_ONBOARDING_BIND 10.12.194.1
ensure_env_setting BOXBRAIN_AGENT_MODE advisory
ensure_env_setting BOXBRAIN_AI_PROVIDER ""
ensure_env_setting BOXBRAIN_DRIVE_DEVICE_ID ""
ensure_env_setting BOXBRAIN_DRIVE_REMOTE boxbrain-drive
ensure_env_setting BOXBRAIN_DRIVE_CONFIG /var/lib/boxbrain/identity/rclone.conf
ensure_env_setting BOXBRAIN_DRIVE_EXPECTED_ACCOUNT boxbrainprime@gmail.com

# Version 0.5 used an all-interface onboarding bind. Migrate only that known
# default; preserve any explicit operator-selected address.
if grep -q '^BOXBRAIN_ONBOARDING_BIND=0\.0\.0\.0$' /etc/boxbrain/boxbrain.env; then
    sed -i 's/^BOXBRAIN_ONBOARDING_BIND=0\.0\.0\.0$/BOXBRAIN_ONBOARDING_BIND=10.12.194.1/' \
        /etc/boxbrain/boxbrain.env
fi

systemctl daemon-reload
systemctl enable boxbrain.service boxbrain-onboarding.service boxbrain-link-monitor.service
systemctl enable boxbrain-rescue-early.service
systemctl enable boxbrain-hid-kvm.service
systemctl restart boxbrain.service boxbrain-onboarding.service boxbrain-link-monitor.service
systemctl is-active --quiet boxbrain.service
systemctl is-active --quiet boxbrain-onboarding.service
systemctl is-active --quiet boxbrain-link-monitor.service

if [ -e /etc/boxbrain/usb-keyboard-enabled ] && \
    systemctl is-active --quiet boxbrain-usb-gadget.service; then
    systemctl restart boxbrain-hid-kvm.service
    systemctl is-active --quiet boxbrain-hid-kvm.service
fi

attempt=0
until /usr/local/bin/boxbrainctl health >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 15 ]; then
        echo "BoxBrain started but did not become ready in time." >&2
        exit 1
    fi
    sleep 1
done

printf 'BoxBrain Kali Pi edge agent installed and running.\n'
