#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo 'Run bootstrap-oci-arm.sh as root on the new OCI ARM instance.' >&2
  exit 2
fi
if [ "$(uname -m)" != aarch64 ]; then
  echo 'Refusing to configure a non-aarch64 instance.' >&2
  exit 2
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  build-essential ca-certificates ccache git podman python3
if ! id aurum-arm >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/aurum-arm --create-home --shell /usr/sbin/nologin aurum-arm
fi
if ! grep -q '^aurum-arm:' /etc/subuid; then
  usermod --add-subuids 100000-165535 aurum-arm
fi
if ! grep -q '^aurum-arm:' /etc/subgid; then
  usermod --add-subgids 100000-165535 aurum-arm
fi
install -d -o aurum-arm -g aurum-arm -m 0750 /var/lib/aurum-arm/evidence /usr/local/lib/aurum-arm
install -o root -g root -m 0755 "$script_dir/run-verifier.sh" /usr/local/lib/aurum-arm/run-verifier.sh
install -o root -g root -m 0644 "$script_dir/aurum-arm-verifier.service" /etc/systemd/system/aurum-arm-verifier.service
install -o root -g root -m 0644 "$script_dir/aurum-arm-verifier.timer" /etc/systemd/system/aurum-arm-verifier.timer
systemctl daemon-reload
systemctl enable --now aurum-arm-verifier.timer
echo 'AURUM_OCI_ARM_BOOTSTRAP_OK authority=VERIFY-ONLY repository_credentials=none'
