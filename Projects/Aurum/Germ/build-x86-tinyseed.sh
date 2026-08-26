#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../../.." && pwd)
BUILD_ROOT=${AURUM_TINYSEED_BUILD_ROOT:-"$SCRIPT_DIR/.build-x86"}
DIST="$REPO_ROOT/dist"
IMAGE="$DIST/Aurum-TinySeed-amd64.iso"

if [ "$(id -u)" -ne 0 ]; then
  echo "build-x86-tinyseed.sh must run as root" >&2
  exit 2
fi
command -v lb >/dev/null 2>&1 || { echo "live-build is required" >&2; exit 2; }

rm -rf "$BUILD_ROOT"
mkdir -p "$BUILD_ROOT" "$DIST"
cd "$BUILD_ROOT"

lb config \
  --mode debian \
  --distribution bookworm \
  --architecture amd64 \
  --binary-image iso-hybrid \
  --system live \
  --debian-installer none \
  --archive-areas "main non-free-firmware" \
  --apt-recommends false \
  --security true \
  --updates true \
  --linux-packages linux-image \
  --linux-flavours amd64 \
  --bootloaders "syslinux grub-efi" \
  --uefi-secure-boot disable \
  --checksums sha256 \
  --memtest none \
  --bootappend-live "boot=live components edd=off quiet plymouth.enable=0 aurum.ui=compact vt.global_cursor_default=0 console=tty0 console=ttyS0,115200n8" \
  --iso-application "Aurum Tiny Seed" \
  --iso-publisher "FormatX66/BoxBrain" \
  --iso-volume "AURUM_TINY"

mkdir -p config/package-lists
cat > config/package-lists/tinyseed.list.chroot <<'EOF'
live-boot
systemd-sysv
udev
python3
git
ca-certificates
openssl
network-manager
systemd-resolved
iproute2
iputils-ping
iw
rfkill
wireless-regdb
firmware-iwlwifi
firmware-realtek
firmware-atheros
firmware-brcm80211
firmware-misc-nonfree
parted
rsync
dosfstools
e2fsprogs
util-linux
kbd
kmod
alsa-utils
espeakup
pciutils
usbutils
grub-efi-amd64-bin
grub-pc-bin
grub2-common
EOF

# Keep the normal unattended path first, but carry a prepared safe/verbose
# fallback for real hardware that blanks the display or hides an early failure.
# Mirror GRUB to the serial port as well as the display so UEFI boot failures
# preserve bootloader evidence before Linux is alive. This does not change the
# kernel boot gate; it only makes the pre-kernel path observable.
for grub_dir in grub-pc grub-efi; do
  mkdir -p "config/bootloaders/$grub_dir"
  cat > "config/bootloaders/$grub_dir/grub.cfg" <<'EOF'
serial --unit=0 --speed=115200 --word=8 --parity=no --stop=1
terminal_input console serial
terminal_output console serial
# EFI has no native VGA text handoff. Register its video adapters for the
# Linux boot protocol, but keep GRUB itself on the compact firmware console.
if [ "$grub_platform" = "efi" ]; then
    insmod all_video
    set gfxpayload=keep
fi
set default=0
set timeout=3
set color_normal=light-gray/black
set color_highlight=yellow/black
menuentry "Aurum Tiny Seed" {
    linux @KERNEL_LIVE@ @APPEND_LIVE@
    initrd @INITRD_LIVE@
}
menuentry "Aurum Tiny Seed (safe verbose)" {
    linux @KERNEL_LIVE@ @APPEND_LIVE@ aurum.ui=plain nomodeset systemd.show_status=yes loglevel=7
    initrd @INITRD_LIVE@
}
menuentry "Aurum Tiny Seed (spoken / blind)" {
    linux @KERNEL_LIVE@ @APPEND_LIVE@ aurum.accessibility=blind aurum.ui=plain speakup.synth=soft systemd.show_status=yes
    initrd @INITRD_LIVE@
}
EOF
done

# Debian live-build's Syslinux/ISOLINUX default timeout is 0, which pauses
# indefinitely for a key press. Tiny Seed must boot unattended on legacy BIOS.
# A second manual entry is intentionally verbose and graphics-conservative.
mkdir -p config/bootloaders/isolinux config/bootloaders/syslinux
cat > config/bootloaders/isolinux/isolinux.cfg <<'EOF'
ui menu.c32
default aurum
prompt 0
timeout 30
menu title Aurum Tiny Seed
menu color title 1;36;40 #ff33d6ff #00000000 std
menu color sel 1;33;40 #ffffd75f #00000000 std
menu color unsel 0;37;40 #ffd0d0d0 #00000000 std
label aurum
  menu label Aurum Tiny Seed
  kernel /live/vmlinuz
  append initrd=/live/initrd.img boot=live components edd=off quiet plymouth.enable=0 aurum.ui=compact vt.global_cursor_default=0 console=tty0 console=ttyS0,115200n8
label aurum-safe
  menu label Aurum Tiny Seed (safe verbose)
  kernel /live/vmlinuz
  append initrd=/live/initrd.img boot=live components edd=off plymouth.enable=0 aurum.ui=plain nomodeset systemd.show_status=yes loglevel=7 console=tty0 console=ttyS0,115200n8
label aurum-spoken
  menu label Aurum Tiny Seed (spoken / blind)
  kernel /live/vmlinuz
  append initrd=/live/initrd.img boot=live components edd=off plymouth.enable=0 aurum.accessibility=blind aurum.ui=plain speakup.synth=soft systemd.show_status=yes console=tty0 console=ttyS0,115200n8
EOF
cat > config/bootloaders/syslinux/syslinux.cfg <<'EOF'
ui menu.c32
default aurum
prompt 0
timeout 30
menu title Aurum Tiny Seed
menu color title 1;36;40 #ff33d6ff #00000000 std
menu color sel 1;33;40 #ffffd75f #00000000 std
menu color unsel 0;37;40 #ffd0d0d0 #00000000 std
label aurum
  menu label Aurum Tiny Seed
  kernel /live/vmlinuz
  append initrd=/live/initrd.img boot=live components edd=off quiet plymouth.enable=0 aurum.ui=compact vt.global_cursor_default=0 console=tty0 console=ttyS0,115200n8
label aurum-safe
  menu label Aurum Tiny Seed (safe verbose)
  kernel /live/vmlinuz
  append initrd=/live/initrd.img boot=live components edd=off plymouth.enable=0 aurum.ui=plain nomodeset systemd.show_status=yes loglevel=7 console=tty0 console=ttyS0,115200n8
label aurum-spoken
  menu label Aurum Tiny Seed (spoken / blind)
  kernel /live/vmlinuz
  append initrd=/live/initrd.img boot=live components edd=off plymouth.enable=0 aurum.accessibility=blind aurum.ui=plain speakup.synth=soft systemd.show_status=yes console=tty0 console=ttyS0,115200n8
EOF

GERM_DST=config/includes.chroot/usr/lib/aurum/germ
mkdir -p "$GERM_DST"
for name in GENETICS.json carrier.py reseed.py guardian.py recovery_ledger.py bridge.py germ_console.py machine.py network.py installer.py tinyseed.py accessibility.py bootstrap_console.py proof.py rollback_drill.py recovery_control.py recovery_poller.py triage.py; do
  cp "$SCRIPT_DIR/$name" "$GERM_DST/$name"
done
chmod 0755 "$GERM_DST"/*.py
chmod 0644 "$GERM_DST/GENETICS.json"

# Carry one reproducible, policy-pinned x86 phenotype beside the germ.  This is
# an emergency fallback only: online regrowth still resolves current genetics.
# The carrier can grow only the inactive slot and remains subject to the same
# preboot test, Guardian trial, health promotion, journal, and rollback gates.
PLATFORM_COMMIT=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["platforms"]["x86_64"]["offline_carrier"]["pinned_commit"])' "$SCRIPT_DIR/GENETICS.json")
GENETICS_COMMIT=$(git -c safe.directory="$REPO_ROOT" -C "$REPO_ROOT" rev-parse HEAD)
CARRIER_SOURCE="$BUILD_ROOT/carrier-platform-source"
mkdir -p "$CARRIER_SOURCE"
git -c safe.directory="$REPO_ROOT" -C "$REPO_ROOT" fetch --depth=1 https://github.com/FormatX66/BoxBrain.git "$PLATFORM_COMMIT"
test "$(git -c safe.directory="$REPO_ROOT" -C "$REPO_ROOT" rev-parse FETCH_HEAD)" = "$PLATFORM_COMMIT"
git -c safe.directory="$REPO_ROOT" -C "$REPO_ROOT" archive "$PLATFORM_COMMIT" Projects/AurumPC Projects/Codelation | tar -x -C "$CARRIER_SOURCE"
python3 "$SCRIPT_DIR/carrier.py" build \
  --genetics-root "$REPO_ROOT" \
  --platform-root "$CARRIER_SOURCE" \
  --output config/includes.chroot/usr/lib/aurum/carrier \
  --genetics-commit "$GENETICS_COMMIT" \
  --platform-commit "$PLATFORM_COMMIT" \
  --architecture x86_64

# Remote recovery is fail-closed. The trust policy is always embedded; the
# public authority is embedded only after the protected enrollment workflow has
# published it. Without that public key, recovery_poller.py returns disabled.
RECOVERY_SRC="$REPO_ROOT/Projects/Aurum/Recovery"
mkdir -p config/includes.chroot/etc/aurum
cp "$RECOVERY_SRC/trusted-refs.json" config/includes.chroot/etc/aurum/recovery-trusted-refs.json
if [ -f "$RECOVERY_SRC/authority-public.pem" ]; then
  cp "$RECOVERY_SRC/authority-public.pem" config/includes.chroot/etc/aurum/recovery-authority.pem
  chmod 0644 config/includes.chroot/etc/aurum/recovery-authority.pem
fi
chmod 0644 config/includes.chroot/etc/aurum/recovery-trusted-refs.json

mkdir -p config/includes.chroot/var/lib/aurum/slots/A/opt/aurum
cp "$SCRIPT_DIR/bootstrap_console.py" config/includes.chroot/var/lib/aurum/slots/A/opt/aurum/aurum_console.py
chmod 0755 config/includes.chroot/var/lib/aurum/slots/A/opt/aurum/aurum_console.py
mkdir -p config/includes.chroot/opt
ln -s /var/lib/aurum/slots/A/opt/aurum config/includes.chroot/opt/aurum
mkdir -p config/includes.chroot/var/lib/aurum/germ
cat > config/includes.chroot/var/lib/aurum/germ/slots.json <<'EOF'
{
  "schema": "aurum-germ-slots-v1",
  "active": "A",
  "lkg": "A",
  "trial": null,
  "trial_boots": 0,
  "quarantined": [],
  "last_result": "tiny-seed-bootstrap"
}
EOF

mkdir -p config/includes.chroot/usr/sbin
cat > config/includes.chroot/usr/sbin/aurum-reseed <<'EOF'
#!/bin/sh
exec /usr/bin/python3 /usr/lib/aurum/germ/reseed.py "$@"
EOF
cat > config/includes.chroot/usr/sbin/aurum-rollback-drill <<'EOF'
#!/bin/sh
exec /usr/bin/python3 /usr/lib/aurum/germ/rollback_drill.py "$@"
EOF
cat > config/includes.chroot/usr/sbin/aurum-recovery-poll <<'EOF'
#!/bin/sh
exec /usr/bin/python3 /usr/lib/aurum/germ/recovery_poller.py "$@"
EOF
cat > config/includes.chroot/usr/sbin/aurum-triage <<'EOF'
#!/bin/sh
exec /usr/bin/python3 /usr/lib/aurum/germ/triage.py "$@"
EOF
chmod 0755 config/includes.chroot/usr/sbin/aurum-reseed config/includes.chroot/usr/sbin/aurum-rollback-drill config/includes.chroot/usr/sbin/aurum-recovery-poll config/includes.chroot/usr/sbin/aurum-triage

mkdir -p config/includes.chroot/etc/NetworkManager/conf.d
cat > config/includes.chroot/etc/NetworkManager/conf.d/10-aurum-resolved.conf <<'EOF'
[main]
dns=systemd-resolved
rc-manager=symlink
EOF

SYSTEMD=config/includes.chroot/etc/systemd/system
WANTS=$SYSTEMD/multi-user.target.wants
TIMERS=$SYSTEMD/timers.target.wants
mkdir -p "$WANTS" "$TIMERS"
mkdir -p "$SYSTEMD/espeakup.service.d"
cat > "$SYSTEMD/espeakup.service.d/aurum-blind-only.conf" <<'EOF'
[Unit]
ConditionKernelCommandLine=aurum.accessibility=blind
EOF
cat > "$SYSTEMD/aurum-triage.service" <<'EOF'
[Unit]
Description=Aurum read-only failure triage receipt
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/lib/aurum/germ/triage.py
StandardOutput=journal+console
StandardError=journal+console
EOF
cat > "$SYSTEMD/aurum-resolver-link.service" <<'EOF'
[Unit]
Description=Restore the Tiny Seed live resolver link
After=local-fs.target
Before=NetworkManager.service
[Service]
Type=oneshot
ExecStart=/bin/ln -sfn /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf
[Install]
WantedBy=multi-user.target
EOF
cat > "$SYSTEMD/aurum-germ-preflight.service" <<'EOF'
[Unit]
Description=Aurum protected germ preflight
After=local-fs.target
Before=aurum-tinyseed.service
OnFailure=aurum-triage.service
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/lib/aurum/germ/guardian.py preflight --reboot-on-rollback
[Install]
WantedBy=multi-user.target
EOF
cat > "$SYSTEMD/aurum-germ-health.service" <<'EOF'
[Unit]
Description=Aurum protected germ candidate health gate
After=aurum-germ-preflight.service
OnFailure=aurum-triage.service
[Service]
Type=oneshot
ExecStartPre=/bin/sleep 8
ExecStart=/usr/bin/python3 /usr/lib/aurum/germ/guardian.py health-check --reboot-on-rollback
[Install]
WantedBy=multi-user.target
EOF
cat > "$SYSTEMD/aurum-accessibility.service" <<'EOF'
[Unit]
Description=Aurum Tiny Seed spoken startup
ConditionKernelCommandLine=aurum.accessibility=blind
After=systemd-modules-load.service sound.target
Before=aurum-tinyseed.service
OnFailure=aurum-triage.service
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/lib/aurum/germ/accessibility.py
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
EOF
cat > "$SYSTEMD/aurum-tinyseed.service" <<'EOF'
[Unit]
Description=Aurum Tiny Seed setup
After=aurum-resolver-link.service NetworkManager-wait-online.service systemd-resolved.service aurum-germ-preflight.service aurum-accessibility.service
Wants=aurum-resolver-link.service NetworkManager-wait-online.service systemd-resolved.service
Conflicts=getty@tty1.service
OnFailure=aurum-triage.service
[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/lib/aurum/germ/tinyseed.py
StandardInput=tty-force
StandardOutput=tty
StandardError=tty
TTYPath=/dev/tty1
TTYReset=yes
TTYVHangup=yes
Restart=on-failure
RestartSec=2
[Install]
WantedBy=multi-user.target
EOF
cat > "$SYSTEMD/aurum-tinyseed-smoke.service" <<'EOF'
[Unit]
Description=Aurum Tiny Seed smoke marker
After=local-fs.target
[Service]
Type=oneshot
ExecStart=/bin/sh -c 'test -s /usr/lib/aurum/germ/GENETICS.json && test -x /usr/lib/aurum/germ/reseed.py && echo AURUM_TINYSEED_READY > /dev/console; if [ -c /dev/ttyS0 ]; then echo AURUM_TINYSEED_READY > /dev/ttyS0; fi'
[Install]
WantedBy=multi-user.target
EOF
cat > "$SYSTEMD/aurum-boot-proof.service" <<'EOF'
[Unit]
Description=Aurum non-secret boot proof receipt
After=local-fs.target aurum-germ-preflight.service
OnFailure=aurum-triage.service
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/lib/aurum/germ/proof.py
StandardOutput=journal+console
StandardError=journal+console
[Install]
WantedBy=multi-user.target
EOF
cat > "$SYSTEMD/aurum-recovery-poll.service" <<'EOF'
[Unit]
Description=Aurum signed remote recovery desired-state check
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/lib/aurum/germ/recovery_poller.py
SuccessExitStatus=2
NoNewPrivileges=true
EOF
cat > "$SYSTEMD/aurum-recovery-poll.timer" <<'EOF'
[Unit]
Description=Periodically check Aurum signed recovery desired state
[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
RandomizedDelaySec=30s
Persistent=true
Unit=aurum-recovery-poll.service
[Install]
WantedBy=timers.target
EOF
for unit in aurum-resolver-link.service aurum-germ-preflight.service aurum-germ-health.service aurum-accessibility.service aurum-tinyseed.service aurum-tinyseed-smoke.service aurum-boot-proof.service; do
  ln -s "../$unit" "$WANTS/$unit"
done
ln -s "../aurum-recovery-poll.timer" "$TIMERS/aurum-recovery-poll.timer"
ln -s /lib/systemd/system/NetworkManager.service "$WANTS/NetworkManager.service"
ln -s /lib/systemd/system/systemd-resolved.service "$WANTS/systemd-resolved.service"
ln -s /dev/null "$SYSTEMD/getty@tty1.service"

mkdir -p config/includes.chroot/etc
printf '%s\n' aurum-tinyseed > config/includes.chroot/etc/hostname
cat > config/includes.chroot/etc/motd <<'EOF'
Aurum Tiny Seed
Git stores the genetics. Tiny Seed carries the germ. The machine grows Aurum.
If something fails after boot, run: aurum-triage
EOF

mkdir -p config/hooks/live
cat > config/hooks/live/010-tinyseed.hook.chroot <<'EOF'
#!/bin/sh
set -eu
chmod 0755 /usr/lib/aurum/germ/*.py /usr/sbin/aurum-reseed /usr/sbin/aurum-rollback-drill /usr/sbin/aurum-recovery-poll /usr/sbin/aurum-triage
EOF
chmod 0755 config/hooks/live/010-tinyseed.hook.chroot

lb build
ISO=$(find . -maxdepth 1 -type f \( -name 'live-image-amd64*.hybrid.iso' -o -name 'live-image-amd64*.iso' \) | head -n 1)
[ -n "${ISO:-}" ] && [ -s "$ISO" ] || { echo "Tiny Seed build produced no ISO" >&2; exit 1; }
cp "$ISO" "$IMAGE"
(
  cd "$REPO_ROOT"
  sha256sum dist/Aurum-TinySeed-amd64.iso > dist/Aurum-TinySeed-amd64.iso.sha256
)
echo "AURUM_TINYSEED_X86_BUILD_OK image=$IMAGE"
