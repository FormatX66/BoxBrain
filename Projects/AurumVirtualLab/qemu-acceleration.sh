#!/usr/bin/env bash

# Source this file from a GitHub verification step, then call
# select_aurum_qemu_acceleration with the immutable builder image reference.
select_aurum_qemu_acceleration() {
  local builder_image=${1:?builder image is required}

  AURUM_QEMU_ACCEL=tcg
  AURUM_QEMU_EXECUTION_ENVIRONMENT=qemu-uefi-tcg
  AURUM_QEMU_DOCKER_ARGS=()

  if [ -c /dev/kvm ] && sudo chmod 0666 /dev/kvm; then
    if docker run --rm --device /dev/kvm "$builder_image" bash -lc '
      set -euo pipefail
      qemu-system-x86_64 \
        -machine q35,accel=kvm \
        -cpu qemu64 \
        -nodefaults \
        -display none \
        -monitor none \
        -S \
        -daemonize \
        -pidfile /tmp/aurum-kvm-probe.pid
      kill "$(cat /tmp/aurum-kvm-probe.pid)"
    '
    then
      AURUM_QEMU_ACCEL=kvm
      AURUM_QEMU_EXECUTION_ENVIRONMENT=qemu-uefi-kvm
      AURUM_QEMU_DOCKER_ARGS=(--device /dev/kvm)
    fi
  fi

  export AURUM_QEMU_ACCEL AURUM_QEMU_EXECUTION_ENVIRONMENT
  echo "AURUM_QEMU_ROUTE selected=$AURUM_QEMU_ACCEL environment=$AURUM_QEMU_EXECUTION_ENVIRONMENT"
}
