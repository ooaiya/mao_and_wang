#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
exec "${OOMLAB_PYTHON:-python3}" -m oomlab.cli prepare "$@"
