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

# Ubuntu 24.04 currently ships an older live-build that still emits the retired
# Debian security suite path "bookworm/updates". v0.01 is a disposable live
# image, so disable only that legacy security stanza while retaining Bookworm
# and bookworm-updates. This avoids accepting an invalid repository definition.
lb config \
  --mode debian \
  --distribution bookworm \
  --architectures amd64 \
  --binary-images iso-hybrid \
  --system live \
  --debian-installer none \
  --archive-areas main \
  --apt-recommends false \
  --security false \
  --memtest none \
  --bootappend-live "boot=live components quiet console=tty0 console=ttyS0,115200n8" \
  --iso-application "Aurum PC v0.01" \
  --iso-publisher "FormatX66/BoxBrain" \
  --iso-volume "AURUM_PC_001"

mkdir -p config/package-lists
cat > config/package-lists/aurum.list.chroot <<'EOF'
linux-image-amd64
live-boot
systemd-sysv
python3
iproute2
pciutils
usbutils
ca-certificates
grub-pc-bin
grub-efi-amd64-bin
EOF

mkdir -p config/includes.chroot/opt/aurum
cp "$SCRIPT_DIR/aurum_console.py" config/includes.chroot/opt/aurum/aurum_console.py
chmod 0755 config/includes.chroot/opt/aurum/aurum_console.py
cp -a "$REPO_ROOT/Projects/Codelation" config/includes.chroot/opt/aurum/codelation

mkdir -p config/includes.chroot/etc/systemd/system
cat > config/includes.chroot/etc/systemd/system/aurum-pc-console.service <<'EOF'
[Unit]
Description=Aurum PC primary console
After=local-fs.target systemd-udev-trigger.service
Conflicts=getty@tty1.service
ConditionPathExists=/dev/tty1

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/aurum/aurum_console.py
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
find /opt/aurum/codelation -type f -name '*.py' -exec chmod 0644 {} +
EOF
chmod 0755 config/hooks/live/010-aurum-permissions.hook.chroot

lb build

ISO=$(find . -maxdepth 1 -type f \( -name 'live-image-amd64*.hybrid.iso' -o -name 'live-image-amd64*.iso' \) | head -n 1)
if [ -z "${ISO:-}" ] || [ ! -f "$ISO" ]; then
  echo "live-build completed without an ISO." >&2
  exit 1
fi
cp "$ISO" "$DIST/$IMAGE_NAME"
sha256sum "$DIST/$IMAGE_NAME" > "$DIST/$IMAGE_NAME.sha256"
ls -lh "$DIST/$IMAGE_NAME" "$DIST/$IMAGE_NAME.sha256"
