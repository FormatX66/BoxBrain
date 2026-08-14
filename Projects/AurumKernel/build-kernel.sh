#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
BUILD_ROOT="$SCRIPT_DIR/.build"
DIST="$REPO_ROOT/dist/Aurum-Kernel-v0.01-x86_64"
ARCH=${AURUM_ARCH:-x86_64}

if [ "$ARCH" != "x86_64" ]; then
  echo "This OS-parity reference lane currently builds x86_64; ARM64 uses the same staged architecture when its reference boot lane is added." >&2
  exit 2
fi
if ! command -v make >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
  echo "make and python3 are required." >&2
  exit 2
fi
if ! command -v cpio >/dev/null 2>&1 || ! command -v gzip >/dev/null 2>&1; then
  echo "cpio and gzip are required." >&2
  exit 2
fi
if ! command -v busybox >/dev/null 2>&1; then
  echo "busybox-static is required for the verification initramfs." >&2
  exit 2
fi

rm -rf "$BUILD_ROOT" "$DIST"
mkdir -p "$BUILD_ROOT" "$DIST"

if [ -n "${AURUM_KERNEL_SOURCE:-}" ]; then
  KERNEL_SOURCE=$(CDPATH= cd -- "$AURUM_KERNEL_SOURCE" && pwd)
else
  SOURCE_ARCHIVE=$(find /usr/src -maxdepth 1 -type f -name 'linux-source-*.tar.xz' | sort | tail -n 1)
  if [ -z "${SOURCE_ARCHIVE:-}" ] || [ ! -f "$SOURCE_ARCHIVE" ]; then
    echo "No Debian linux-source archive found under /usr/src." >&2
    exit 2
  fi
  mkdir -p "$BUILD_ROOT/source"
  tar -xf "$SOURCE_ARCHIVE" -C "$BUILD_ROOT/source"
  KERNEL_SOURCE=$(find "$BUILD_ROOT/source" -mindepth 1 -maxdepth 1 -type d -name 'linux-source-*' | sort | tail -n 1)
fi

if [ ! -f "$KERNEL_SOURCE/Makefile" ] || [ ! -f "$KERNEL_SOURCE/Kconfig" ]; then
  echo "Resolved kernel source is not a Linux kernel source tree: $KERNEL_SOURCE" >&2
  exit 2
fi

BASE_CONFIG="$BUILD_ROOT/seed.config"
if [ -n "${AURUM_BASE_CONFIG:-}" ]; then
  cp "$AURUM_BASE_CONFIG" "$BASE_CONFIG"
  BASE_CONFIG_SOURCE=machine-seed
else
  CONFIG_OUT="$BUILD_ROOT/reference-config"
  mkdir -p "$CONFIG_OUT"
  make -C "$KERNEL_SOURCE" O="$CONFIG_OUT" ARCH=x86 defconfig
  "$KERNEL_SOURCE/scripts/config" --file "$CONFIG_OUT/.config" \
    -e MODULES \
    -e BLK_DEV_INITRD \
    -e RD_GZIP \
    -e BINFMT_SCRIPT \
    -e DEVTMPFS \
    -e DEVTMPFS_MOUNT \
    -e TTY \
    -e PRINTK \
    -e SERIAL_8250 \
    -e SERIAL_8250_CONSOLE
  make -C "$KERNEL_SOURCE" O="$CONFIG_OUT" ARCH=x86 olddefconfig
  cp "$CONFIG_OUT/.config" "$BASE_CONFIG"
  BASE_CONFIG_SOURCE=debian-reference-defconfig
fi

OUTPUT_DIR="$BUILD_ROOT/output"
MODULE_STAGE="$BUILD_ROOT/module-stage"
JOBS=${AURUM_BUILD_JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)}

export PYTHONPATH="$REPO_ROOT/Projects/Codelation"
export AURUM_BUILD_SOURCE="$KERNEL_SOURCE"
export AURUM_BUILD_OUTPUT="$OUTPUT_DIR"
export AURUM_BUILD_STAGE="$MODULE_STAGE"
export AURUM_BUILD_CONFIG="$BASE_CONFIG"
export AURUM_BUILD_JOBS="$JOBS"
export AURUM_BUILD_LSMOD="${AURUM_LSMOD_FILE:-}"
python3 - <<'PY'
import os
from pathlib import Path
from kernel_selfbuild.compiler import KernelCompileRequest, compile_kernel

lsmod = os.environ.get("AURUM_BUILD_LSMOD") or None
request = KernelCompileRequest(
    architecture="x86_64",
    source_dir=Path(os.environ["AURUM_BUILD_SOURCE"]),
    output_dir=Path(os.environ["AURUM_BUILD_OUTPUT"]),
    stage_dir=Path(os.environ["AURUM_BUILD_STAGE"]),
    base_config=Path(os.environ["AURUM_BUILD_CONFIG"]),
    jobs=int(os.environ["AURUM_BUILD_JOBS"]),
    lsmod_file=Path(lsmod) if lsmod else None,
)
manifest = compile_kernel(request)
print(manifest.to_dict())
PY

cp "$OUTPUT_DIR/arch/x86/boot/bzImage" "$DIST/bzImage"
cp "$OUTPUT_DIR/.config" "$DIST/kernel.config"
cp "$OUTPUT_DIR/aurum-kernel-manifest.json" "$DIST/aurum-kernel-manifest.json"

if [ -d "$MODULE_STAGE/lib/modules" ]; then
  tar -C "$MODULE_STAGE" -czf "$DIST/modules.tar.gz" .
else
  mkdir -p "$MODULE_STAGE"
  tar -C "$MODULE_STAGE" -czf "$DIST/modules.tar.gz" .
fi

INITROOT="$BUILD_ROOT/initramfs"
mkdir -p "$INITROOT/bin" "$INITROOT/proc" "$INITROOT/sys" "$INITROOT/dev"
cp "$(command -v busybox)" "$INITROOT/bin/busybox"
ln -s busybox "$INITROOT/bin/sh"
cat > "$INITROOT/init" <<'EOF'
#!/bin/sh
/bin/busybox mount -t proc proc /proc 2>/dev/null || true
/bin/busybox mount -t sysfs sysfs /sys 2>/dev/null || true
echo 'AURUM_KERNEL_READY version=0.01 arch=x86_64'
echo 'selftest=ok'
exec /bin/sh
EOF
chmod 0755 "$INITROOT/init"
(
  cd "$INITROOT"
  find . -print | cpio -o -H newc --quiet | gzip -9
) > "$DIST/initramfs.cpio.gz"

make -s -C "$KERNEL_SOURCE" ARCH=x86 kernelversion > "$DIST/kernel-version.txt"
printf '%s\n' "$BASE_CONFIG_SOURCE" > "$DIST/base-config-source.txt"

cd "$REPO_ROOT"
sha256sum \
  dist/Aurum-Kernel-v0.01-x86_64/bzImage \
  dist/Aurum-Kernel-v0.01-x86_64/initramfs.cpio.gz \
  dist/Aurum-Kernel-v0.01-x86_64/kernel.config \
  dist/Aurum-Kernel-v0.01-x86_64/modules.tar.gz \
  dist/Aurum-Kernel-v0.01-x86_64/aurum-kernel-manifest.json \
  > dist/Aurum-Kernel-v0.01-x86_64/SHA256SUMS

ls -lh "$DIST"
