#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
VERSION=${AURUM_KERNEL_VERSION:-0.02}
SOURCE_REPOSITORY=${AURUM_PI3_SOURCE_REPOSITORY:-https://github.com/raspberrypi/linux.git}
SOURCE_COMMIT=${AURUM_PI3_KERNEL_COMMIT:-73b1c785241360882ab9f7fb0793e775c25db325}
BUILD_ROOT=${AURUM_PI3_KERNEL_WORK_ROOT:-$SCRIPT_DIR/.build-pi3}
DIST=${AURUM_PI3_KERNEL_DIST:-$REPO_ROOT/dist/Aurum-Pi3-Kernel-v${VERSION}-arm64}
JOBS=${AURUM_BUILD_JOBS:-unknown}

for tool in python3 aarch64-linux-gnu-gcc cpio gzip sha256sum tar make; do
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
    raise SystemExit(f"Refusing build root outside the repository or user cache: {build}")
if dist_root not in dist.parents:
    raise SystemExit(f"Refusing dist root outside the repository dist tree: {dist}")
if build == dist or build in dist.parents or dist in build.parents:
    raise SystemExit(f"Refusing overlapping build and dist roots: {build} / {dist}")
PY

SOURCE="$BUILD_ROOT/source"
OUTPUT="$BUILD_ROOT/output"
STAGE="$BUILD_ROOT/module-stage"
test -d "$SOURCE/.git"
test "$(git -C "$SOURCE" rev-parse HEAD)" = "$SOURCE_COMMIT"
test -s "$OUTPUT/arch/arm64/boot/Image"
test -s "$OUTPUT/.config"
test -s "$OUTPUT/aurum-kernel-manifest.json"
test -d "$STAGE/lib/modules"

rm -rf -- "$DIST"
mkdir -p "$DIST/dtbs" "$DIST/overlays"
cp "$OUTPUT/arch/arm64/boot/Image" "$DIST/kernel8-aurum.img"
cp "$OUTPUT/.config" "$DIST/kernel.config"
cp "$OUTPUT/aurum-kernel-manifest.json" "$DIST/aurum-kernel-manifest.json"
for board in bcm2710-rpi-3-b.dtb bcm2710-rpi-3-b-plus.dtb; do
  test -s "$OUTPUT/arch/arm64/boot/dts/broadcom/$board"
  cp "$OUTPUT/arch/arm64/boot/dts/broadcom/$board" "$DIST/dtbs/$board"
done
test -s "$OUTPUT/arch/arm64/boot/dts/broadcom/bcm2837-rpi-3-a-plus.dtb"
cp "$OUTPUT/arch/arm64/boot/dts/broadcom/bcm2837-rpi-3-a-plus.dtb" \
  "$DIST/dtbs/bcm2710-rpi-3-a-plus.dtb"
cp "$OUTPUT/arch/arm64/boot/dts/overlays/"*.dtbo "$DIST/overlays/"
if [ -f "$OUTPUT/arch/arm64/boot/dts/overlays/README" ]; then
  cp "$OUTPUT/arch/arm64/boot/dts/overlays/README" "$DIST/overlays/README"
fi
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner \
  -C "$STAGE" -czf "$DIST/modules.tar.gz" .

INITROOT="$BUILD_ROOT/initramfs"
mkdir -p "$INITROOT"
aarch64-linux-gnu-gcc -static -Os -s \
  -DAURUM_KERNEL_VERSION=\"$VERSION\" \
  -o "$INITROOT/init" "$SCRIPT_DIR/pi3-init.c"
(
  cd "$INITROOT"
  find . -print | cpio -o -H newc --quiet | gzip -9
) > "$DIST/pi3-initramfs.cpio.gz"

make -s -C "$SOURCE" O="$OUTPUT" ARCH=arm64 \
  CROSS_COMPILE=aarch64-linux-gnu- kernelrelease > "$DIST/kernel-release.txt"
printf '%s\n' "$SOURCE_REPOSITORY" > "$DIST/source-repository.txt"
printf '%s\n' "$SOURCE_COMMIT" > "$DIST/source-commit.txt"
printf '%s\n' "$JOBS" > "$DIST/build-jobs.txt"
aarch64-linux-gnu-gcc --version | head -n 1 > "$DIST/cross-compiler.txt"

(
  cd "$DIST"
  find . -type f ! -name SHA256SUMS -print0 \
    | sort -z \
    | xargs -0 sha256sum > SHA256SUMS
  sha256sum -c SHA256SUMS
)
printf 'AURUM_PI3_KERNEL_BUILD_COMPLETE bundle=%s commit=%s\n' \
  "$DIST" "$SOURCE_COMMIT"
