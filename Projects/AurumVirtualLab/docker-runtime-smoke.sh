#!/bin/sh
set -eu

EXPECTED_ARCH=${1:-unknown}
ACTUAL_ARCH=$(uname -m)

echo "AURUM_DOCKER_RUNTIME expected=$EXPECTED_ARCH actual=$ACTUAL_ARCH"
case "$EXPECTED_ARCH:$ACTUAL_ARCH" in
  amd64:x86_64|arm64:aarch64|arm64:arm64) ;;
  *) echo "Architecture mismatch: expected $EXPECTED_ARCH, got $ACTUAL_ARCH" >&2; exit 1 ;;
esac

python3 -m py_compile \
  Projects/AurumPC/aurum_console.py \
  Projects/AurumPC/aurum_workspace.py \
  Projects/AurumPi3/aurum_pi3_console.py \
  Projects/AurumPi3/aurum_updater.py \
  Projects/AurumPi3/aurum_release_gate.py \
  Projects/AurumPi3/build-runtime-release.py \
  Projects/AurumVirtualLab/convergence_gate.py

python3 -m unittest discover -s Projects/AurumPC/tests -v
python3 -m unittest discover -s Projects/AurumPi3/tests -v

SMOKE_ROOT=/tmp/aurum-vlab-runtime
rm -rf "$SMOKE_ROOT"
mkdir -p "$SMOKE_ROOT"
ln -s /workspace/Projects/Codelation "$SMOKE_ROOT/codelation"
cat > "$SMOKE_ROOT/RELEASE.json" <<'EOF'
{
  "architecture": "arm64",
  "release_id": "virtual-lab-runtime-smoke",
  "target": "raspberry-pi-3",
  "version": "0.03.0"
}
EOF

AURUM_ROOT="$SMOKE_ROOT" \
AURUM_CAPABILITY_STATE="/tmp/aurum-pi3-capability-state.json" \
python3 Projects/AurumPi3/aurum_pi3_console.py --selftest-json \
  | tee /tmp/aurum-runtime-selftest.json

grep -q '"selftest": "ok"' /tmp/aurum-runtime-selftest.json

echo "AURUM_DOCKER_RUNTIME_OK arch=$EXPECTED_ARCH"
