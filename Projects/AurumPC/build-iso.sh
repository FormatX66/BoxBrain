#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
BUILD_ROOT=${AURUM_PC_BUILD_ROOT:-"$SCRIPT_DIR/.build"}
DIST="$REPO_ROOT/dist"
IMAGE_NAME="Aurum-PC-v0.01-amd64.iso"
PERSISTENT_CACHE_ROOT=${AURUM_LB_CACHE_DIR:-}

if [ "$(id -u)" -ne 0 ]; then
  echo "build-iso.sh must run as root (live-build uses chroot/mount operations)." >&2
  exit 2
fi
if ! command -v lb >/dev/null 2>&1; then
  echo "live-build (lb) is required." >&2
  exit 2
fi
if [ ! -d "$REPO_ROOT/Projects/Codelation" ]; then
  echo "Projects/Codelation is missing." >&2
  exit 2
fi

rm -rf "$BUILD_ROOT"
mkdir -p "$BUILD_ROOT" "$DIST"

if [ -n "$PERSISTENT_CACHE_ROOT" ]; then
  case "$PERSISTENT_CACHE_ROOT" in
    /*) ;;
    *) echo "AURUM_LB_CACHE_DIR must be an absolute path." >&2; exit 2 ;;
  esac
  mkdir -p "$PERSISTENT_CACHE_ROOT" "$BUILD_ROOT/cache"
  # A reflink is copy-on-write where supported and an ordinary copy otherwise.
  # Never hard-link a speculative build to trusted cache content: a failed build
  # must be unable to modify the previously committed cache through an inode.
  cp -a --reflink=auto "$PERSISTENT_CACHE_ROOT/." "$BUILD_ROOT/cache/"
  echo "AURUM_LIVE_BUILD_CACHE_STAGED source=$PERSISTENT_CACHE_ROOT"
fi
cd "$BUILD_ROOT"

# Physical discovery is intentionally stateless at the root filesystem layer.
# A raw reflash can leave an old persistence partition at the end of a USB
# device; automatically mounting it as a root overlay can mix old /opt/aurum
# code with a new ISO. Do not request live persistence until Aurum explicitly
# provisions a versioned state-only volume.
lb config \
  --mode debian \
  --distribution bookworm \
  --architecture amd64 \
  --binary-image iso-hybrid \
  --system live \
  --debian-installer none \
  --archive-areas "main non-free-firmware" \
  --apt-recommends false \
  --apt-source-archives false \
  --security true \
  --updates true \
  --cache true \
  --cache-indices false \
  --cache-packages true \
  --linux-packages "linux-image" \
  --linux-flavours "amd64" \
  --bootloaders "syslinux grub-efi" \
  --uefi-secure-boot disable \
  --checksums sha256 \
  --zsync false \
  --memtest none \
  --bootappend-live "boot=live components quiet preempt=voluntary transparent_hugepage=madvise console=tty0 console=ttyS0,115200n8" \
  --iso-application "Aurum PC v0.01" \
  --iso-publisher "FormatX66/BoxBrain" \
  --iso-volume "AURUM_PC_001"

# live-build 20230502 has no command-line token for an empty stage-cache list:
# the string "false" is treated as a stage name. Keep only validated package
# files across runs; never restore a bootstrap/chroot/rootfs stage.
sed -i 's/^LB_CACHE_STAGES=.*/LB_CACHE_STAGES=""/' config/common

mkdir -p config/package-lists
cat > config/package-lists/aurum.list.chroot <<'EOF'
live-boot
systemd-sysv
systemd-timesyncd
udev
python3
python3-pygame
iproute2
kmod
pciutils
usbutils
ca-certificates
git
systemd-resolved
wpasupplicant
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
grub-efi-amd64-bin
grub2-common
build-essential
linux-headers-amd64
xserver-xorg
xserver-xorg-input-libinput
xinit
x11-xserver-utils
libinput-tools
chromium
openssh-server
novnc
sudo
websockify
x11vnc
EOF

GRUB_FONT=/usr/share/grub/unicode.pf2
if [ ! -s "$GRUB_FONT" ]; then
  echo "Required GRUB font is missing: $GRUB_FONT" >&2
  exit 1
fi
mkdir -p config/includes.binary/boot/grub/fonts
cp "$GRUB_FONT" config/includes.binary/boot/grub/fonts/unicode.pf2

mkdir -p config/bootloaders/grub-pc
cat > config/bootloaders/grub-pc/grub.cfg <<'EOF'
set default=0
set timeout=0

menuentry "Aurum PC v0.01" {
    linux @KERNEL_LIVE@ @APPEND_LIVE@
    initrd @INITRD_LIVE@
}
EOF

mkdir -p config/includes.chroot/opt/aurum
for f in aurum_arcade.py aurum_autonomy.py aurum_boot_screen.py aurum_console.py aurum_bootstrap.py aurum_control_plane.py aurum_credential_bootstrap.py aurum_desktop.py aurum_desktop_runtime.py aurum_display_runtime.py aurum_driver_synthesis.py aurum_echo_native.py aurum_gpt_executor.py aurum_gpt_trait.py aurum_gui_runtime.py aurum_hardware.py aurum_hopper_gui.py aurum_input.py aurum_network.py aurum_pointer_motion.py aurum_projection_runtime.py aurum_remote_command.py aurum_remote_control.py aurum_runtime_update.py aurum_self_debug.py aurum_sync_recovery.py aurum_time.py aurum_traits.py aurum_web_surface.py aurum_wifi_diag.py aurum_wifi_persistence.py aurum_wifi_recovery.py aurum_workspace.py aurum_installer.py; do
  cp "$SCRIPT_DIR/$f" "config/includes.chroot/opt/aurum/$f"
  chmod 0755 "config/includes.chroot/opt/aurum/$f"
done
cp "$SCRIPT_DIR/pc01_autonomy_policy.json" config/includes.chroot/opt/aurum/pc01_autonomy_policy.json
chmod 0644 config/includes.chroot/opt/aurum/pc01_autonomy_policy.json
cp -a "$REPO_ROOT/Projects/Codelation" config/includes.chroot/opt/aurum/codelation
mkdir -p config/includes.chroot/usr/lib/aurum
cp "$REPO_ROOT/Projects/Codelation/autobuild/native_chain_state.json" config/includes.chroot/usr/lib/aurum/native-chain-state.json
chmod 0644 config/includes.chroot/usr/lib/aurum/native-chain-state.json
mkdir -p config/includes.chroot/var/lib/aurum/state config/includes.chroot/var/lib/aurum/workspace

mkdir -p config/includes.chroot/etc/systemd/system config/includes.chroot/etc/systemd/network
cat > config/includes.chroot/etc/systemd/network/20-aurum-wired.network <<'EOF'
[Match]
Name=en* eth* usb*

[Network]
DHCP=yes
IPv6AcceptRA=yes
EOF
cat > config/includes.chroot/etc/systemd/network/25-aurum-wireless.network <<'EOF'
[Match]
Name=wl*

[Network]
DHCP=yes
IPv6AcceptRA=yes
EOF

# Hopper's touchpad and external mice share one deterministic libinput path.
# Tapping remains a presentation choice; runtime power is handled separately.
RUNTIME_ASSETS="$REPO_ROOT/Projects/AurumPC/runtime-assets"
install -D -m 0644 \
  "$RUNTIME_ASSETS/etc/X11/xorg.conf.d/40-aurum-libinput.conf" \
  config/includes.chroot/etc/X11/xorg.conf.d/40-aurum-libinput.conf
install -D -m 0644 \
  "$RUNTIME_ASSETS/etc/systemd/system/aurum-input-bootstrap.service" \
  config/includes.chroot/etc/systemd/system/aurum-input-bootstrap.service
install -D -m 0644 \
  "$RUNTIME_ASSETS/etc/systemd/system/aurum-pc-console.service" \
  config/includes.chroot/etc/systemd/system/aurum-pc-console.service
install -D -m 0755 \
  "$RUNTIME_ASSETS/usr/lib/systemd/system-sleep/aurum-input-wake" \
  config/includes.chroot/usr/lib/systemd/system-sleep/aurum-input-wake
install -D -m 0644 \
  "$RUNTIME_ASSETS/etc/systemd/system/aurum-remote-bootstrap.service" \
  config/includes.chroot/etc/systemd/system/aurum-remote-bootstrap.service
install -D -m 0644 \
  "$RUNTIME_ASSETS/etc/ssh/sshd_config.d/60-aurum-remote.conf" \
  config/includes.chroot/etc/ssh/sshd_config.d/60-aurum-remote.conf
install -D -m 0440 \
  "$RUNTIME_ASSETS/etc/sudoers.d/aurum-remote" \
  config/includes.chroot/etc/sudoers.d/aurum-remote

cat > config/includes.chroot/etc/systemd/system/aurum-pc-serial.service <<'EOF'
[Unit]
Description=Aurum PC serial verification console
After=local-fs.target systemd-udev-trigger.service
Conflicts=serial-getty@ttyS0.service
ConditionPathExists=/dev/ttyS0

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/aurum/aurum_bootstrap.py
Environment=PYTHONUNBUFFERED=1
Environment=AURUM_PRIMARY_CONSOLE=0
Environment=AURUM_DISABLE_AUTONOMOUS_FIRST_BOOT=1
Environment=MALLOC_ARENA_MAX=2
Nice=5
IOSchedulingClass=best-effort
IOSchedulingPriority=6
OOMScoreAdjust=-100
StandardInput=tty-force
StandardOutput=tty
StandardError=tty
TTYPath=/dev/ttyS0
TTYReset=yes
TTYVHangup=yes
Restart=always
RestartSec=1

[Install]
WantedBy=multi-user.target
EOF

mkdir -p config/includes.chroot/etc/systemd/system/multi-user.target.wants
ln -s ../aurum-input-bootstrap.service config/includes.chroot/etc/systemd/system/multi-user.target.wants/aurum-input-bootstrap.service
ln -s ../aurum-pc-console.service config/includes.chroot/etc/systemd/system/multi-user.target.wants/aurum-pc-console.service
ln -s ../aurum-pc-serial.service config/includes.chroot/etc/systemd/system/multi-user.target.wants/aurum-pc-serial.service
ln -s ../aurum-remote-bootstrap.service config/includes.chroot/etc/systemd/system/multi-user.target.wants/aurum-remote-bootstrap.service
ln -s /lib/systemd/system/ssh.service config/includes.chroot/etc/systemd/system/multi-user.target.wants/ssh.service
ln -s /lib/systemd/system/systemd-networkd.service config/includes.chroot/etc/systemd/system/multi-user.target.wants/systemd-networkd.service
ln -s /lib/systemd/system/systemd-resolved.service config/includes.chroot/etc/systemd/system/multi-user.target.wants/systemd-resolved.service
ln -s /dev/null config/includes.chroot/etc/systemd/system/getty@tty1.service
ln -s /dev/null config/includes.chroot/etc/systemd/system/serial-getty@ttyS0.service

printf '%s\n' 'aurum-pc' > config/includes.chroot/etc/hostname
cat > config/includes.chroot/etc/motd <<'EOF'
Aurum PC v0.01
Linux is present only as the temporary hardware compatibility substrate.
The exposed operator surface is the bounded Aurum console; no arbitrary shell is offered.
Physical discovery boots statelessly so stale USB persistence cannot replace the bundled runtime.
EOF

mkdir -p config/hooks/live
cat > config/hooks/live/010-aurum-permissions.hook.chroot <<'EOF'
#!/bin/sh
set -eu
chmod 0755 /opt/aurum/*.py
find /opt/aurum/codelation -type f -name '*.py' -exec chmod 0644 {} +
ln -sfn /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf
EOF
chmod 0755 config/hooks/live/010-aurum-permissions.hook.chroot

lb build

ISO=$(find . -maxdepth 1 -type f \( -name 'live-image-amd64*.hybrid.iso' -o -name 'live-image-amd64*.iso' \) | head -n 1)
if [ -z "${ISO:-}" ] || [ ! -f "$ISO" ]; then
  echo "live-build completed without an ISO." >&2
  exit 1
fi
cp "$ISO" "$DIST/$IMAGE_NAME"
(
  cd "$REPO_ROOT"
  sha256sum "dist/$IMAGE_NAME" > "dist/$IMAGE_NAME.sha256"
)

# Provenance is part of the cache transaction. A package cache becomes trusted
# only after the exact bundled control-plane source and serial boot contract
# have been recovered from the completed ISO and verified.
bash "$REPO_ROOT/Projects/AurumBuild/verify-pc-image.sh" \
  "$DIST/$IMAGE_NAME" "$DIST/$IMAGE_NAME.sha256"

if [ -n "$PERSISTENT_CACHE_ROOT" ]; then
  # Commit reusable packages only after the complete image, sidecar, and
  # source/image provenance verification exist.
  # A failed/speculative build therefore cannot contaminate trusted cache state.
  # Exclude indices, Contents files, and cached build stages. Debian validates
  # every restored package against the freshly downloaded signed indices.
  rsync -a --delete --delete-excluded \
    --include='/packages.*/' \
    --include='/packages.*/***' \
    --exclude='*' \
    "$BUILD_ROOT/cache/" "$PERSISTENT_CACHE_ROOT/"
  echo "AURUM_LIVE_BUILD_CACHE_COMMITTED target=$PERSISTENT_CACHE_ROOT"
fi

ls -lh "$DIST/$IMAGE_NAME" "$DIST/$IMAGE_NAME.sha256"
