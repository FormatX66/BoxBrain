#!/usr/bin/env bash
# Shared by the hosted backend job and the Codex cloud Python environment.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
python --version
python -m pip install --disable-pip-version-check \
  -e ./Projects/AurumFarmer -e './controller[dev]'
python -m pip check
