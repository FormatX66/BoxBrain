#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
BUILD_ROOT="$SCRIPT_DIR/.build-trackpad"
DIST="$REPO_ROOT/dist"
IMAGE_NAME="Aurum-PC-v0.01-trackpad-exp-amd64.iso"

if [ "$(id -u)" -ne 0 ]; then
  echo "build-iso-trackpad.sh must run as root (live-build uses chroot/mount operations)." >&2
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
  --iso-application "Aurum PC v0.01 Trackpad Experimental" \
  --iso-publisher "FormatX66/BoxBrain" \
  --iso-volume "AURUM_PC_TPAD"

mkdir -p config/package-lists
cat > config/package-lists/aurum.list.chroot <<'EOF'
live-boot
systemd-sysv
udev
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
libinput-tools
xserver-xorg-core
xserver-xorg-input-libinput
xinit
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
for file in aurum_console.py aurum_workspace.py aurum_installer.py aurum_input.py; do
  cp "$SCRIPT_DIR/$file" "config/includes.chroot/opt/aurum/$file"
  chmod 0755 "config/includes.chroot/opt/aurum/$file"
done
cp -a "$REPO_ROOT/Projects/Codelation" config/includes.chroot/opt/aurum/codelation
mkdir -p config/includes.chroot/usr/lib/aurum
cp "$REPO_ROOT/Projects/Codelation/autobuild/native_chain_state.json" \
  config/includes.chroot/usr/lib/aurum/native-chain-state.json
chmod 0644 config/includes.chroot/usr/lib/aurum/native-chain-state.json
mkdir -p config/includes.chroot/var/lib/aurum/state config/includes.chroot/var/lib/aurum/workspace

# Give Xorg a deterministic libinput policy when the Aurum graphical surface starts.
mkdir -p config/includes.chroot/etc/X11/xorg.conf.d
cat > config/includes.chroot/etc/X11/xorg.conf.d/40-aurum-libinput.conf <<'EOF'
Section "InputClass"
    Identifier "Aurum libinput pointer"
    MatchIsPointer "on"
    Driver "libinput"
    Option "AccelProfile" "adaptive"
EndSection

Section "InputClass"
    Identifier "Aurum libinput touchpad"
    MatchIsTouchpad "on"
    Driver "libinput"
    Option "Tapping" "on"
    Option "DisableWhileTyping" "on"
    Option "NaturalScrolling" "false"
EndSection
EOF

mkdir -p config/includes.chroot/etc/systemd/system
mkdir -p config/includes.chroot/etc/systemd/network
cat > config/includes.chroot/etc/systemd/network/20-aurum-wired.network <<'EOF'
[Match]
Name=en* eth*

[Network]
DHCP=yes
IPv6AcceptRA=yes
EOF

# Internal laptop touchpads commonly arrive through I2C-HID or PS/2, while
# external mice generally arrive through USB HID. Probe all four paths and let
# udev/libinput classify the actual device. Failed modprobes are harmless when
# a driver is built into the kernel or the hardware path is absent.
cat > config/includes.chroot/etc/systemd/system/aurum-input-bootstrap.service <<'EOF'
[Unit]
Description=Aurum pointer and trackpad bootstrap
After=systemd-udev-trigger.service
Before=aurum-pc-console.service

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'modprobe i2c_hid_acpi 2>/dev/null || true; modprobe hid_multitouch 2>/dev/null || true; modprobe psmouse 2>/dev/null || true; modprobe usbhid 2>/dev/null || true; udevadm settle --timeout=10 || true; /usr/bin/python3 /opt/aurum/aurum_input.py > /run/aurum-input-status.json || true'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

cat > config/includes.chroot/etc/systemd/system/aurum-pc-console.service <<'EOF'
[Unit]
Description=Aurum PC primary console
After=local-fs.target systemd-udev-trigger.service aurum-input-bootstrap.service
Requires=aurum-input-bootstrap.service
Conflicts=getty@tty1.service
ConditionPathExists=/dev/tty1

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/aurum/aurum_console.py
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
ExecStart=/usr/bin/python3 /opt/aurum/aurum_console.py
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
ln -s ../aurum-input-bootstrap.service config/includes.chroot/etc/systemd/system/multi-user.target.wants/aurum-input-bootstrap.service
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
chmod 0755 /opt/aurum/aurum_workspace.py
chmod 0755 /opt/aurum/aurum_installer.py
chmod 0755 /opt/aurum/aurum_input.py
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
ls -lh "$DIST/$IMAGE_NAME" "$DIST/$IMAGE_NAME.sha256"
