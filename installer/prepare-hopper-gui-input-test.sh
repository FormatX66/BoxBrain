#!/bin/sh
# Pull and activate the bounded Hopper GUI/input test lane without reflashing.
set -eu

BRANCH=${AURUM_HOPPER_TEST_BRANCH:-aurum/hopper-gui-input-test-20260821}
WORKSPACE=${AURUM_GIT_WORKSPACE:-/var/lib/aurum/workspace/BoxBrain}
STATE_DIR=${AURUM_STATE_DIR:-/var/lib/aurum/state}

if [ "$(id -u)" -ne 0 ]; then
  echo "prepare-hopper-gui-input-test.sh requires the root-owned Aurum console." >&2
  exit 2
fi
if [ ! -f /etc/aurum-installed.json ]; then
  echo "Refusing Hopper test activation: installed Aurum receipt is missing." >&2
  exit 2
fi
if [ ! -d "$WORKSPACE/.git" ]; then
  echo "Refusing Hopper test activation: Aurum Git workspace is missing." >&2
  exit 2
fi
if [ -n "$(git -C "$WORKSPACE" status --porcelain)" ]; then
  echo "Refusing Hopper test activation: Aurum workspace has local changes." >&2
  exit 2
fi

previous_head=$(git -C "$WORKSPACE" rev-parse HEAD)
previous_branch=$(git -C "$WORKSPACE" symbolic-ref --quiet --short HEAD || printf '%s' detached)
git -C "$WORKSPACE" fetch --no-tags origin "refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
if git -C "$WORKSPACE" show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git -C "$WORKSPACE" switch "$BRANCH"
  git -C "$WORKSPACE" merge --ff-only "origin/$BRANCH"
else
  git -C "$WORKSPACE" switch --create "$BRANCH" --track "origin/$BRANCH"
fi

install -d -m 0755 /etc/X11/xorg.conf.d /etc/systemd/system /usr/lib/systemd/system-sleep
cat > /etc/X11/xorg.conf.d/40-aurum-libinput.conf <<'EOF'
Section "InputClass"
    Identifier "Aurum libinput pointer"
    MatchIsPointer "on"
    Driver "libinput"
    Option "AccelProfile" "adaptive"
EndSection

Section "InputClass"
    Identifier "Aurum libinput touchpad"
    MatchIsTouchpad "on"
    Driver "libinput"
    Option "Tapping" "on"
    Option "DisableWhileTyping" "on"
    Option "NaturalScrolling" "false"
EndSection
EOF

cat > /etc/systemd/system/aurum-input-bootstrap.service <<'EOF'
[Unit]
Description=Aurum mouse and trackpad wake bootstrap
After=systemd-udev-trigger.service
Before=aurum-pc-console.service

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'modprobe i2c_hid_acpi 2>/dev/null || true; modprobe hid_multitouch 2>/dev/null || true; modprobe psmouse 2>/dev/null || true; modprobe usbhid 2>/dev/null || true; udevadm settle --timeout=10 || true; /usr/bin/python3 /opt/aurum/aurum_input.py --apply-wake-policy --write-state /run/aurum-input-status.json || true'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

cat > /usr/lib/systemd/system-sleep/aurum-input-wake <<'EOF'
#!/bin/sh
set -u
if [ "${1:-}" = post ]; then
  /usr/bin/python3 /opt/aurum/aurum_input.py \
    --apply-wake-policy --write-state /run/aurum-input-status.json \
    >/run/aurum-input-resume.log 2>&1 || true
fi
EOF
chmod 0755 /usr/lib/systemd/system-sleep/aurum-input-wake

python3 "$WORKSPACE/Projects/AurumPC/aurum_runtime_update.py" plan >/run/aurum-hopper-test-plan.json
python3 "$WORKSPACE/Projects/AurumPC/aurum_runtime_update.py" apply >/run/aurum-hopper-test-apply.json
systemctl daemon-reload
systemctl enable aurum-input-bootstrap.service >/dev/null
systemctl restart aurum-input-bootstrap.service

install -d -m 0700 "$STATE_DIR"
python3 - "$STATE_DIR/hopper-gui-input-test.json" "$BRANCH" "$previous_branch" "$previous_head" <<'PY'
import json
import os
import sys
import time
from pathlib import Path

path = Path(sys.argv[1])
payload = {
    "schema": "aurum.hopper-gui-input-test.v1",
    "status": "ready-for-physical-test",
    "branch": sys.argv[2],
    "previous_branch": sys.argv[3],
    "previous_head": sys.argv[4],
    "activated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "reboot_required": False,
    "physical_checks": ["boot-screen", "mouse-click", "trackpad-tap", "post-resume-pointer"],
}
temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.chmod(temporary, 0o600)
os.replace(temporary, path)
print(json.dumps(payload, sort_keys=True))
PY
