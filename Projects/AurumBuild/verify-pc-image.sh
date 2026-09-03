#!/usr/bin/env bash
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
iso=${1:-$repository_root/dist/Aurum-PC-v0.01-amd64.iso}
checksum=${2:-$repository_root/dist/Aurum-PC-v0.01-amd64.iso.sha256}

if [ ! -s "$iso" ]; then
  echo "Aurum PC provenance input is missing or empty: $iso" >&2
  exit 2
fi
if [ ! -s "$checksum" ]; then
  echo "Aurum PC checksum input is missing or empty: $checksum" >&2
  exit 2
fi

verify_dir=$(mktemp -d /tmp/aurum-iso-verify.XXXXXX)
cleanup() { rm -rf -- "$verify_dir"; }
trap cleanup EXIT

if ! xorriso -osirrox on \
  -indev "$iso" \
  -extract /live/filesystem.squashfs "$verify_dir/filesystem.squashfs" \
  >"$verify_dir/xorriso.log" 2>&1
then
  echo "Aurum PC provenance could not extract /live/filesystem.squashfs." >&2
  cat "$verify_dir/xorriso.log" >&2
  exit 1
fi

source_sha=$(sha256sum "$repository_root/Projects/AurumPC/aurum_console.py" | awk '{print $1}')
if ! unsquashfs -cat "$verify_dir/filesystem.squashfs" opt/aurum/aurum_console.py \
  >"$verify_dir/aurum_console.py"
then
  echo "Aurum PC provenance could not read /opt/aurum/aurum_console.py." >&2
  exit 1
fi
image_sha=$(sha256sum "$verify_dir/aurum_console.py" | awk '{print $1}')
if [ "$source_sha" != "$image_sha" ]; then
  echo "Aurum PC source/image provenance mismatch: source_sha=$source_sha image_sha=$image_sha" >&2
  exit 1
fi

# A successful build must ship the exact input path and graphical setup that
# passed the image-local SDL tests, not only the console verified above.
while IFS='|' read -r source_path image_path; do
  expected=$(sha256sum "$repository_root/$source_path" | awk '{print $1}')
  unsquashfs -cat "$verify_dir/filesystem.squashfs" "$image_path" >"$verify_dir/input-payload"
  observed=$(sha256sum "$verify_dir/input-payload" | awk '{print $1}')
  if [ "$expected" != "$observed" ]; then
    echo "Aurum PC input source/image provenance mismatch: $image_path" >&2
    exit 1
  fi
done <<'EOF'
Projects/AurumPC/aurum_setup_gui.py|opt/aurum/aurum_setup_gui.py
Projects/AurumPC/aurum_input.py|opt/aurum/aurum_input.py
Projects/AurumPC/runtime-assets/etc/systemd/system/aurum-setup.service|etc/systemd/system/aurum-setup.service
Projects/AurumPC/runtime-assets/etc/systemd/system/aurum-input-bootstrap.service|etc/systemd/system/aurum-input-bootstrap.service
Projects/AurumPC/runtime-assets/etc/X11/xorg.conf.d/40-aurum-libinput.conf|etc/X11/xorg.conf.d/40-aurum-libinput.conf
EOF
echo AURUM_INPUT_IMAGE_PROVENANCE_VERIFIED

python3 - "$verify_dir/aurum_console.py" <<'PY'
import ast
import pathlib
import sys

tree = ast.parse(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
constants = {
    node.value
    for node in ast.walk(tree)
    if isinstance(node, ast.Constant) and isinstance(node.value, str)
}
if not any(value.startswith("AURUM_PC_READY version=") for value in constants):
    raise SystemExit("embedded console lost the runtime-ready marker")
versions = {
    node.value.value
    for node in ast.walk(tree)
    if isinstance(node, ast.Assign)
    and any(isinstance(target, ast.Name) and target.id == "VERSION" for target in node.targets)
    and isinstance(node.value, ast.Constant)
}
if versions != {"0.01"}:
    raise SystemExit(f"embedded console version mismatch: {versions}")
PY

if ! unsquashfs -cat "$verify_dir/filesystem.squashfs" etc/systemd/system/aurum-pc-serial.service \
  >"$verify_dir/aurum-pc-serial.service"
then
  echo "Aurum PC provenance could not read aurum-pc-serial.service." >&2
  exit 1
fi
if ! grep -F "ExecStart=/usr/bin/python3 /opt/aurum/aurum_bootstrap.py" \
  "$verify_dir/aurum-pc-serial.service" >/dev/null
then
  echo "Aurum PC image is missing its serial verification service contract." >&2
  exit 1
fi

(cd "$repository_root" && sha256sum -c "$checksum")
echo "AURUM_PC_ISO_PROVENANCE verified=true source_sha=$source_sha image_sha=$image_sha"
