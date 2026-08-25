#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
VERSION=${AURUM_KERNEL_VERSION:-0.02}
SOURCE_REPOSITORY=https://github.com/raspberrypi/linux.git
SOURCE_COMMIT=${AURUM_PI3_KERNEL_COMMIT:-73b1c785241360882ab9f7fb0793e775c25db325}
BUILD_ROOT=${AURUM_PI3_KERNEL_WORK_ROOT:-$SCRIPT_DIR/.build-pi3}
DIST=${AURUM_PI3_KERNEL_DIST:-$REPO_ROOT/dist/Aurum-Pi3-Kernel-v${VERSION}-arm64}

case "$VERSION" in
  *[!A-Za-z0-9._-]*|'') echo "AURUM_KERNEL_VERSION is invalid." >&2; exit 2 ;;
esac
case "$SOURCE_COMMIT" in
  *[!0-9a-f]*|'') echo "AURUM_PI3_KERNEL_COMMIT must be a hexadecimal commit." >&2; exit 2 ;;
esac
if [ "${#SOURCE_COMMIT}" -ne 40 ]; then
  echo "AURUM_PI3_KERNEL_COMMIT must be a full 40-character commit." >&2
  exit 2
fi
for tool in git make python3 aarch64-linux-gnu-gcc cpio gzip sha256sum tar; do
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
SOURCE="$BUILD_ROOT/source"
OUTPUT="$BUILD_ROOT/output"
STAGE="$BUILD_ROOT/module-stage"
CONFIG_OUT="$BUILD_ROOT/reference-config"

git init -q "$SOURCE"
git -C "$SOURCE" remote add origin "$SOURCE_REPOSITORY"
git -C "$SOURCE" fetch --depth=1 origin "$SOURCE_COMMIT"
git -C "$SOURCE" checkout -q --detach FETCH_HEAD
RESOLVED_COMMIT=$(git -C "$SOURCE" rev-parse HEAD)
if [ "$RESOLVED_COMMIT" != "$SOURCE_COMMIT" ]; then
  echo "Raspberry Pi kernel source commit mismatch." >&2
  exit 1
fi

mkdir -p "$CONFIG_OUT"
make -C "$SOURCE" O="$CONFIG_OUT" ARCH=arm64 \
  CROSS_COMPILE=aarch64-linux-gnu- bcm2711_defconfig
"$SOURCE/scripts/config" --file "$CONFIG_OUT/.config" \
  --set-str LOCALVERSION "-aurum-pi3-v$VERSION" \
  -d LOCALVERSION_AUTO \
  -e MODULES \
  -e BLK_DEV_INITRD \
  -e RD_GZIP \
  -e DEVTMPFS \
  -e DEVTMPFS_MOUNT \
  -e TTY \
  -e PRINTK \
  -e SERIAL_AMBA_PL011 \
  -e SERIAL_AMBA_PL011_CONSOLE
make -C "$SOURCE" O="$CONFIG_OUT" ARCH=arm64 \
  CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
cp "$CONFIG_OUT/.config" "$BUILD_ROOT/seed.config"

if [ -n "${AURUM_BUILD_JOBS:-}" ]; then
  JOBS=$AURUM_BUILD_JOBS
else
  JOBS=$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)
  if [ "$JOBS" -gt 8 ]; then JOBS=8; fi
fi

export PYTHONPATH="$REPO_ROOT/Projects/Codelation"
export AURUM_BUILD_SOURCE="$SOURCE"
export AURUM_BUILD_OUTPUT="$OUTPUT"
export AURUM_BUILD_STAGE="$STAGE"
export AURUM_BUILD_CONFIG="$BUILD_ROOT/seed.config"
export AURUM_BUILD_JOBS="$JOBS"
python3 - <<'PY'
import os
from pathlib import Path
from kernel_selfbuild.compiler import KernelCompileRequest, compile_kernel

request = KernelCompileRequest(
    architecture="arm64",
    source_dir=Path(os.environ["AURUM_BUILD_SOURCE"]),
    output_dir=Path(os.environ["AURUM_BUILD_OUTPUT"]),
    stage_dir=Path(os.environ["AURUM_BUILD_STAGE"]),
    base_config=Path(os.environ["AURUM_BUILD_CONFIG"]),
    jobs=int(os.environ["AURUM_BUILD_JOBS"]),
    build_modules=True,
    extra_build_targets=("dtbs",),
    cross_compile="aarch64-linux-gnu-",
)
print(compile_kernel(request).to_dict())
PY

AURUM_KERNEL_VERSION="$VERSION" \
AURUM_PI3_SOURCE_REPOSITORY="$SOURCE_REPOSITORY" \
AURUM_PI3_KERNEL_COMMIT="$SOURCE_COMMIT" \
AURUM_PI3_KERNEL_WORK_ROOT="$BUILD_ROOT" \
AURUM_PI3_KERNEL_DIST="$DIST" \
AURUM_BUILD_JOBS="$JOBS" \
  sh "$SCRIPT_DIR/package-pi3-kernel.sh"
