#!/usr/bin/env python3
"""Prepare the Gen1 human-integration ISO build without mutating the trusted source branch.

The candidate branch keeps the proven build script intact in git and applies two
idempotent build-time synchronizations to the checked-out working copy:
1. Chromium is installed into the image instead of being fetched on first boot.
2. Every root Aurum runtime module is copied into /opt/aurum so the image cannot
   silently lag the source tree when a new Gen1 capability is added.
"""
from __future__ import annotations

import argparse
from pathlib import Path

REQUIRED_RUNTIME_MODULES = (
    "aurum_console.py",
    "aurum_gui_runtime.py",
    "aurum_hopper_gui.py",
    "aurum_projection_runtime.py",
    "aurum_web_surface.py",
    "aurum_gpt_trait.py",
    "aurum_gpt_executor.py",
    "aurum_control_plane.py",
    "aurum_network.py",
    "aurum_runtime_update.py",
)

PACKAGE_ANCHOR = "libinput-tools\nEOF"
PACKAGE_REPLACEMENT = "libinput-tools\nchromium\nEOF"
COPY_ANCHOR = 'done\ncp "$SCRIPT_DIR/pc01_autonomy_policy.json" config/includes.chroot/opt/aurum/pc01_autonomy_policy.json'
COPY_REPLACEMENT = '''done

# AURUM_GEN1_RUNTIME_SYNC: source/runtime parity is an acceptance invariant.
# The explicit legacy list above remains for provenance compatibility, while
# this bounded root-level glob prevents newer Gen1 modules from being omitted
# from a freshly built image.
for runtime_file in "$SCRIPT_DIR"/aurum_*.py; do
  [ -f "$runtime_file" ] || continue
  runtime_name=$(basename "$runtime_file")
  cp "$runtime_file" "config/includes.chroot/opt/aurum/$runtime_name"
  chmod 0755 "config/includes.chroot/opt/aurum/$runtime_name"
done
cp "$SCRIPT_DIR/pc01_autonomy_policy.json" config/includes.chroot/opt/aurum/pc01_autonomy_policy.json'''


def prepare(path: Path) -> None:
    project_dir = path.parent
    missing = [name for name in REQUIRED_RUNTIME_MODULES if not (project_dir / name).is_file()]
    if missing:
        raise SystemExit("Gen1 runtime source incomplete: " + ", ".join(missing))

    text = path.read_text(encoding="utf-8")

    if "\nchromium\n" not in text:
        if PACKAGE_ANCHOR not in text:
            raise SystemExit("Unable to locate bounded package-list anchor")
        text = text.replace(PACKAGE_ANCHOR, PACKAGE_REPLACEMENT, 1)

    if "AURUM_GEN1_RUNTIME_SYNC" not in text:
        if COPY_ANCHOR not in text:
            raise SystemExit("Unable to locate bounded runtime-copy anchor")
        text = text.replace(COPY_ANCHOR, COPY_REPLACEMENT, 1)

    path.write_text(text, encoding="utf-8")

    verify = path.read_text(encoding="utf-8")
    if "\nchromium\n" not in verify or "AURUM_GEN1_RUNTIME_SYNC" not in verify:
        raise SystemExit("Gen1 build preparation did not verify")
    print("AURUM_GEN1_BUILD_PREPARED chromium=embedded runtime_sync=all-root-aurum-modules")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("build_script", type=Path)
    args = parser.parse_args()
    prepare(args.build_script.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
