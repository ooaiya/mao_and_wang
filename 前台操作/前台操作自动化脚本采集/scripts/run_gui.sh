#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
exec "${KRITA_GUI_PYTHON:-python3}" "$script_dir/collect_krita.py" "$@"
