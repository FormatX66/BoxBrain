#!/usr/bin/env bash
set -euo pipefail

for tool in \
  busybox ccache cpio debootstrap gcc git grub-mkimage lb make mcopy \
  mkfs.vfat mksquashfs parted python3 qemu-img qemu-system-x86_64 \
  sha256sum xorriso
do
  command -v "$tool" >/dev/null || {
    echo "Aurum builder is missing required tool: $tool" >&2
    exit 2
  }
done

test "$(ccache --get-config compiler_check)" = content || {
  echo 'Aurum builder ccache compiler_check is not content.' >&2
  exit 2
}

if [ ! -s /usr/share/aurum-builder/dpkg-versions.txt ]; then
  echo 'Aurum builder package-version evidence is missing.' >&2
  exit 2
fi

if ! { [ -s /usr/share/OVMF/OVMF_CODE.fd ] && [ -s /usr/share/OVMF/OVMF_VARS.fd ]; } && \
   ! { [ -s /usr/share/OVMF/OVMF_CODE_4M.fd ] && [ -s /usr/share/OVMF/OVMF_VARS_4M.fd ]; }
then
  echo 'Aurum builder has no matching OVMF CODE/VARS pair.' >&2
  exit 2
fi

echo 'AURUM_BUILDER_TOOLCHAIN_VERIFIED'
