#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
BUILD_ROOT="$SCRIPT_DIR/.build"
DIST="$REPO_ROOT/dist"
IMAGE_NAME="Aurum-PC-v0.01-amd64.iso"

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
cd "$BUILD_ROOT"

# Build against Debian Bookworm's own live-build implementation. The CI runs
# this recipe inside a Debian Bookworm container so the live-build, bootloader,
# debootstrap, and target distribution contracts stay aligned.
lb config \
  --mode debian \
  --distribution bookworm \
  --architecture amd64 \
  --binary-image iso-hybrid \
  --system live \
  --debian-installer none \
  --archive-areas main \
  --apt-recommends false \
  --apt-source-archives false \
  --security true \
  --updates true \
  --linux-packages "linux-image" \
  --linux-flavours "amd64" \
  --bootloaders "syslinux grub-efi" \
  --uefi-secure-boot disable \
  --checksums sha256 \
  --memtest none \
  --bootappend-live "boot=live components quiet persistence persistence-label=AURUM_PERSIST preempt=voluntary transparent_hugepage=madvise console=tty0 console=ttyS0,115200n8" \
  --iso-application "Aurum PC v0.01" \
  --iso-publisher "FormatX66/BoxBrain" \
  --iso-volume "AURUM_PC_001"

mkdir -p config/package-lists
cat > config/package-lists/aurum.list.chroot <<'EOF'
live-boot
systemd-sysv
python3
iproute2
pciutils
usbutils
ca-certificates
git
systemd-resolved
parted
rsync
dosfstools
e2fsprogs
util-linux
grub-efi-amd64-bin
grub2-common
EOF

# Debian live-build's EFI GRUB config expects this font at boot. With
# apt-recommends disabled it was not being copied into the ISO, leaving OVMF
# at GRUB with: /boot/grub/fonts/unicode.pf2 not found. Put the build host's
# canonical GRUB font into the binary filesystem explicitly and fail closed if
# the toolchain does not provide it.
GRUB_FONT=/usr/share/grub/unicode.pf2
if [ ! -s "$GRUB_FONT" ]; then
  echo "Required GRUB font is missing: $GRUB_FONT" >&2
  exit 1
fi
mkdir -p config/includes.binary/boot/grub/fonts
cp "$GRUB_FONT" config/includes.binary/boot/grub/fonts/unicode.pf2

# The image has only one intended UEFI boot target. Avoid the graphical/menu
# path entirely in the verification image and transfer control directly to the
# live kernel. live-build expands these placeholders after discovering the
# actual kernel/initrd names, so this stays version-independent.
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
cp "$SCRIPT_DIR/aurum_console.py" config/includes.chroot/opt/aurum/aurum_console.py
chmod 0755 config/includes.chroot/opt/aurum/aurum_console.py
cp "$SCRIPT_DIR/aurum_bootstrap.py" config/includes.chroot/opt/aurum/aurum_bootstrap.py
chmod 0755 config/includes.chroot/opt/aurum/aurum_bootstrap.py
cp "$SCRIPT_DIR/aurum_hardware.py" config/includes.chroot/opt/aurum/aurum_hardware.py
chmod 0755 config/includes.chroot/opt/aurum/aurum_hardware.py
cp "$SCRIPT_DIR/aurum_workspace.py" config/includes.chroot/opt/aurum/aurum_workspace.py
chmod 0755 config/includes.chroot/opt/aurum/aurum_workspace.py
cp "$SCRIPT_DIR/aurum_installer.py" config/includes.chroot/opt/aurum/aurum_installer.py
chmod 0755 config/includes.chroot/opt/aurum/aurum_installer.py
cp -a "$REPO_ROOT/Projects/Codelation" config/includes.chroot/opt/aurum/codelation
mkdir -p config/includes.chroot/usr/lib/aurum
cp "$REPO_ROOT/Projects/Codelation/autobuild/native_chain_state.json" \
  config/includes.chroot/usr/lib/aurum/native-chain-state.json
chmod 0644 config/includes.chroot/usr/lib/aurum/native-chain-state.json
mkdir -p config/includes.chroot/var/lib/aurum/state config/includes.chroot/var/lib/aurum/workspace

mkdir -p config/includes.chroot/etc/systemd/system
mkdir -p config/includes.chroot/etc/systemd/network
cat > config/includes.chroot/etc/systemd/network/20-aurum-wired.network <<'EOF'
[Match]
Name=en* eth*

[Network]
DHCP=yes
IPv6AcceptRA=yes
EOF
cat > config/includes.chroot/etc/systemd/system/aurum-pc-console.service <<'EOF'
[Unit]
Description=Aurum PC primary console
After=local-fs.target systemd-udev-trigger.service
Conflicts=getty@tty1.service
ConditionPathExists=/dev/tty1

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/aurum/aurum_bootstrap.py
Environment=PYTHONUNBUFFERED=1
Environment=MALLOC_ARENA_MAX=2
Nice=5
IOSchedulingClass=best-effort
IOSchedulingPriority=6
OOMScoreAdjust=-100
StandardInput=tty-force
StandardOutput=tty
StandardError=tty
TTYPath=/dev/tty1
TTYReset=yes
TTYVHangup=yes
TTYVTDisallocate=yes
Restart=always
RestartSec=1

[Install]
WantedBy=multi-user.target
EOF

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
ln -s ../aurum-pc-console.service config/includes.chroot/etc/systemd/system/multi-user.target.wants/aurum-pc-console.service
ln -s ../aurum-pc-serial.service config/includes.chroot/etc/systemd/system/multi-user.target.wants/aurum-pc-serial.service
ln -s /lib/systemd/system/systemd-networkd.service config/includes.chroot/etc/systemd/system/multi-user.target.wants/systemd-networkd.service
ln -s /lib/systemd/system/systemd-resolved.service config/includes.chroot/etc/systemd/system/multi-user.target.wants/systemd-resolved.service
ln -s /dev/null config/includes.chroot/etc/systemd/system/getty@tty1.service
ln -s /dev/null config/includes.chroot/etc/systemd/system/serial-getty@ttyS0.service

printf '%s\n' 'aurum-pc' > config/includes.chroot/etc/hostname
cat > config/includes.chroot/etc/motd <<'EOF'
Aurum PC v0.01
Linux is present only as the temporary hardware compatibility substrate.
The exposed operator surface is the bounded Aurum console; no arbitrary shell is offered.
EOF

mkdir -p config/hooks/live
cat > config/hooks/live/010-aurum-permissions.hook.chroot <<'EOF'
#!/bin/sh
set -eu
chmod 0755 /opt/aurum/aurum_console.py
chmod 0755 /opt/aurum/aurum_bootstrap.py
chmod 0755 /opt/aurum/aurum_hardware.py
chmod 0755 /opt/aurum/aurum_workspace.py
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
# Write a repository-relative checksum entry so the host-side CI can verify
# the ISO after the Debian build container exits.
(
  cd "$REPO_ROOT"
  sha256sum "dist/$IMAGE_NAME" > "dist/$IMAGE_NAME.sha256"
)
ls -lh "$DIST/$IMAGE_NAME" "$DIST/$IMAGE_NAME.sha256"
