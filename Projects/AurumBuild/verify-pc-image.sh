#!/usr/bin/env bash
set -euo pipefail

iso=${1:-dist/Aurum-PC-v0.01-amd64.iso}
checksum=${2:-dist/Aurum-PC-v0.01-amd64.iso.sha256}
verify_dir=$(mktemp -d /tmp/aurum-iso-verify.XXXXXX)
cleanup() { rm -rf "$verify_dir"; }
trap cleanup EXIT

xorriso -osirrox on \
  -indev "$iso" \
  -extract /live/filesystem.squashfs "$verify_dir/filesystem.squashfs" \
  >"$verify_dir/xorriso.log" 2>&1
source_sha=$(sha256sum Projects/AurumPC/aurum_console.py | awk '{print $1}')
unsquashfs -cat "$verify_dir/filesystem.squashfs" opt/aurum/aurum_console.py \
  > "$verify_dir/aurum_console.py"
image_sha=$(sha256sum "$verify_dir/aurum_console.py" | awk '{print $1}')
if [ "$source_sha" != "$image_sha" ]; then
  echo "Embedded Aurum console source mismatch: source=$source_sha image=$image_sha" >&2
  exit 1
fi

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

unsquashfs -cat "$verify_dir/filesystem.squashfs" etc/systemd/system/aurum-pc-serial.service \
  | grep -Fq "ExecStart=/usr/bin/python3 /opt/aurum/aurum_bootstrap.py"
test -s "$iso"
sha256sum -c "$checksum"
echo "AURUM_PC_ISO_PROVENANCE verified=true source_sha=$source_sha"
