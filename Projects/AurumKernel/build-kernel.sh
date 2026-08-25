#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
VERSION=${AURUM_KERNEL_VERSION:-0.02}
ARCH=${AURUM_ARCH:-x86_64}
BUILD_ROOT=${AURUM_KERNEL_WORK_ROOT:-$SCRIPT_DIR/.build}
DIST=${AURUM_KERNEL_DIST:-$REPO_ROOT/dist/Aurum-Kernel-v${VERSION}-${ARCH}}
BUILD_MODULES=${AURUM_BUILD_MODULES:-0}

case "$VERSION" in
  *[!A-Za-z0-9._-]*|'') echo "AURUM_KERNEL_VERSION is invalid." >&2; exit 2 ;;
esac
if [ "$ARCH" != "x86_64" ]; then
  echo "The reference boot carrier currently supports x86_64 only." >&2
  exit 2
fi
if [ "$BUILD_MODULES" != "0" ] && [ "$BUILD_MODULES" != "1" ]; then
  echo "AURUM_BUILD_MODULES must be 0 or 1." >&2
  exit 2
fi
for tool in make python3 cpio gzip busybox sha256sum tar; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "$tool is required." >&2
    exit 2
  fi
done

BUILD_ROOT=$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$BUILD_ROOT")
DIST=$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$DIST")
python3 - "$BUILD_ROOT" "$DIST" "$REPO_ROOT" <<'PY'
from pathlib import Path
import sys

build, dist, repo = (Path(value).resolve() for value in sys.argv[1:])
cache = (Path.home() / ".cache").resolve()
dist_root = (repo / "dist").resolve()

if repo not in build.parents and cache not in build.parents:
    raise SystemExit(
        f"Refusing build root outside the repository or user cache: {build}"
    )
if dist_root not in dist.parents:
    raise SystemExit(f"Refusing dist root outside the repository dist tree: {dist}")
if build == dist or build in dist.parents or dist in build.parents:
    raise SystemExit(f"Refusing overlapping build and dist roots: {build} / {dist}")
PY

rm -rf -- "$BUILD_ROOT" "$DIST"
mkdir -p "$BUILD_ROOT" "$DIST"

if [ -n "${AURUM_KERNEL_SOURCE:-}" ]; then
  KERNEL_SOURCE=$(CDPATH= cd -- "$AURUM_KERNEL_SOURCE" && pwd)
  SOURCE_ARCHIVE=
else
  SOURCE_ARCHIVE=$(find -L /usr/src -maxdepth 1 -type f \
    \( -name 'linux-source-*.tar.xz' -o -name 'linux-source-*.tar.bz2' \
       -o -name 'linux-source-*.tar.gz' \) | sort | tail -n 1)
  if [ -z "${SOURCE_ARCHIVE:-}" ] || [ ! -f "$SOURCE_ARCHIVE" ]; then
    echo "No packaged Linux source archive found under /usr/src." >&2
    exit 2
  fi
  mkdir -p "$BUILD_ROOT/source"
  tar -xf "$SOURCE_ARCHIVE" -C "$BUILD_ROOT/source"
  KERNEL_SOURCE=$(find "$BUILD_ROOT/source" -mindepth 1 -maxdepth 1 \
    -type d -name 'linux-source-*' | sort | tail -n 1)
fi

if [ ! -f "$KERNEL_SOURCE/Makefile" ] || [ ! -f "$KERNEL_SOURCE/Kconfig" ]; then
  echo "Resolved source is not a Linux kernel tree: $KERNEL_SOURCE" >&2
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
  BASE_CONFIG_SOURCE=reference-defconfig
fi

OUTPUT_DIR="$BUILD_ROOT/output"
MODULE_STAGE="$BUILD_ROOT/module-stage"
if [ -n "${AURUM_BUILD_JOBS:-}" ]; then
  JOBS=$AURUM_BUILD_JOBS
else
  JOBS=$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)
  if [ "$JOBS" -gt 8 ]; then JOBS=8; fi
fi

export PYTHONPATH="$REPO_ROOT/Projects/Codelation"
export AURUM_BUILD_SOURCE="$KERNEL_SOURCE"
export AURUM_BUILD_OUTPUT="$OUTPUT_DIR"
export AURUM_BUILD_STAGE="$MODULE_STAGE"
export AURUM_BUILD_CONFIG="$BASE_CONFIG"
export AURUM_BUILD_JOBS="$JOBS"
export AURUM_BUILD_MODULES="$BUILD_MODULES"
python3 - <<'PY'
import os
from pathlib import Path
from kernel_selfbuild.compiler import KernelCompileRequest, compile_kernel

request = KernelCompileRequest(
    architecture="x86_64",
    source_dir=Path(os.environ["AURUM_BUILD_SOURCE"]),
    output_dir=Path(os.environ["AURUM_BUILD_OUTPUT"]),
    stage_dir=Path(os.environ["AURUM_BUILD_STAGE"]),
    base_config=Path(os.environ["AURUM_BUILD_CONFIG"]),
    jobs=int(os.environ["AURUM_BUILD_JOBS"]),
    build_modules=os.environ["AURUM_BUILD_MODULES"] == "1",
)
print(compile_kernel(request).to_dict())
PY

cp "$OUTPUT_DIR/arch/x86/boot/bzImage" "$DIST/bzImage"
cp "$OUTPUT_DIR/.config" "$DIST/kernel.config"
cp "$OUTPUT_DIR/aurum-kernel-manifest.json" "$DIST/aurum-kernel-manifest.json"

if [ "$BUILD_MODULES" = "1" ] && [ -d "$MODULE_STAGE/lib/modules" ]; then
  tar -C "$MODULE_STAGE" -czf "$DIST/modules.tar.gz" .
else
  mkdir -p "$MODULE_STAGE"
  tar -C "$MODULE_STAGE" -czf "$DIST/modules.tar.gz" .
fi

INITROOT="$BUILD_ROOT/initramfs"
mkdir -p "$INITROOT/bin" "$INITROOT/proc" "$INITROOT/sys" "$INITROOT/dev"
cp "$(command -v busybox)" "$INITROOT/bin/busybox"
ln -s busybox "$INITROOT/bin/sh"
cat > "$INITROOT/init" <<EOF
#!/bin/sh
/bin/busybox mount -t proc proc /proc 2>/dev/null || true
/bin/busybox mount -t sysfs sysfs /sys 2>/dev/null || true
echo 'AURUM_KERNEL_READY version=$VERSION arch=x86_64'
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
printf '%s\n' "$JOBS" > "$DIST/build-jobs.txt"
printf '%s\n' "$BUILD_MODULES" > "$DIST/build-modules.txt"
if [ -n "${SOURCE_ARCHIVE:-}" ]; then
  sha256sum "$SOURCE_ARCHIVE" | sed "s#  .*#  $(basename "$SOURCE_ARCHIVE")#" \
    > "$DIST/source-archive-sha256.txt"
else
  printf '%s\n' 'external-source-tree' > "$DIST/source-archive-sha256.txt"
fi

cd "$DIST"
sha256sum \
  bzImage \
  initramfs.cpio.gz \
  kernel.config \
  modules.tar.gz \
  aurum-kernel-manifest.json \
  kernel-version.txt \
  base-config-source.txt \
  build-jobs.txt \
  build-modules.txt \
  source-archive-sha256.txt \
  > SHA256SUMS
sha256sum -c SHA256SUMS
printf 'AURUM_KERNEL_BUILD_COMPLETE bundle=%s\n' "$DIST"
