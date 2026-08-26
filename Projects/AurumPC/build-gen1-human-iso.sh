#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

python3 "$SCRIPT_DIR/prepare-gen1-human-build.py" "$SCRIPT_DIR/build-iso.sh"

# The preparation step mutates only this candidate checkout. The trusted LKG
# branch and its proven build script remain untouched until VM promotion.
exec bash "$SCRIPT_DIR/build-iso.sh"
