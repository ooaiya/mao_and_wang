#!/usr/bin/env bash
set -euo pipefail
base="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
g++ -std=c++17 -O2 "$base/src/memory_profile.cpp" "$base/src/memory_budget.cpp" \
  "$base/src/memory_planner.cpp" "$base/tools/oracle_plan.cpp" -o "/home/mxt/TeamOOM/build/memshift_oracle_plan"
