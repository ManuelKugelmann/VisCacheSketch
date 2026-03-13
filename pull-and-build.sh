#!/usr/bin/env bash
# pull-and-build.sh — Pull latest changes, run setup, and build Falcor + VisCache.
#
# Usage:  ./pull-and-build.sh [--config Release|Debug] [--preset linux-gcc-ci]
#
# Steps:
#   1. git pull origin <current branch>
#   2. setup.sh  (submodules, packman deps, copy sources, patch CMake)
#   3. cmake --preset ... && cmake --build ...
#
# Safe to re-run: setup.sh is idempotent, cmake reconfigures incrementally.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FALCOR_ROOT="${SCRIPT_DIR}/Falcor"
CONFIG="Release"
PRESET="linux-gcc-ci"

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --config) CONFIG="$2"; shift 2 ;;
        --preset) PRESET="$2"; shift 2 ;;
        *) echo "Usage: $0 [--config Release|Debug] [--preset linux-gcc-ci]"; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Step 1: Pull latest
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo " Step 1: Pull latest changes"
echo "========================================"

BRANCH="$(git -C "$SCRIPT_DIR" rev-parse --abbrev-ref HEAD)"
echo "[build] Branch: $BRANCH"
git -C "$SCRIPT_DIR" pull origin "$BRANCH" || echo "[build] WARNING: pull failed, continuing with current checkout"

# ---------------------------------------------------------------------------
# Step 2: Setup (copies sources, patches CMake, etc.)
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo " Step 2: Setup"
echo "========================================"
bash "$SCRIPT_DIR/setup.sh"

# ---------------------------------------------------------------------------
# Step 3: CMake configure + build
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo " Step 3: CMake configure + build ($PRESET / $CONFIG)"
echo "========================================"

# Use packman cmake if available, otherwise system cmake
CMAKE="cmake"
if [ -x "$FALCOR_ROOT/tools/.packman/cmake/bin/cmake" ]; then
    CMAKE="$FALCOR_ROOT/tools/.packman/cmake/bin/cmake"
fi

echo "[build] Configuring: $CMAKE --preset $PRESET"
"$CMAKE" --preset "$PRESET" -S "$FALCOR_ROOT"

echo "[build] Building: $CMAKE --build ... --config $CONFIG"
"$CMAKE" --build "$FALCOR_ROOT/build/$PRESET" --config "$CONFIG" -j "$(nproc)"

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo " Build complete"
echo "========================================"
echo "[build] Output: $FALCOR_ROOT/build/$PRESET/bin/$CONFIG"
echo ""
