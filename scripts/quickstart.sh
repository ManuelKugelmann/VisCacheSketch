#!/usr/bin/env bash
# quickstart.sh — Run the full VisCacheSketch quickstart sequence.
#
# Usage:  ./scripts/quickstart.sh [--scene Bistro|Sponza|Arcade] [--skip-scenes]
#
# Calls each step in order:
#   1. download_scenes.sh   — fetch test scenes (unless --skip-scenes)
#   2. download_release.sh  — download latest GitHub release
#   3. run-tests.sh         — CPU algorithm tests
#   4. run_release.sh       — smoke test + launch Mogwai
#
# Each script is independently callable. This script just strings them together.
# Idempotent: safe to re-run. Each step skips work already done.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCENE="Bistro"

# shellcheck disable=SC1091
source "$SCRIPT_DIR/version.sh" "quickstart" 2>/dev/null || true
SKIP_SCENES=0

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --scene) SCENE="$2"; shift 2 ;;
        --skip-scenes) SKIP_SCENES=1; shift ;;
        *) echo "Usage: $0 [--scene Bistro|Sponza|Arcade] [--skip-scenes]"; exit 1 ;;
    esac
done

# 1. Download scenes
if [ "$SKIP_SCENES" -eq 1 ]; then
    echo "[quickstart] Skipping scene download (--skip-scenes)"
else
    echo ""
    echo "========================================"
    echo " Step 1: Download test scenes"
    echo "========================================"
    bash "$SCRIPT_DIR/download_scenes.sh" || echo "[quickstart] WARNING: Some scenes failed to download"
fi

# 2. Download release
echo ""
echo "========================================"
echo " Step 2: Download latest release"
echo "========================================"
bash "$SCRIPT_DIR/download_release.sh"

# 3. Run tests
echo ""
echo "========================================"
echo " Step 3: Run tests"
echo "========================================"
bash "$SCRIPT_DIR/run-tests.sh" || echo "[quickstart] WARNING: Some tests failed"

# 4. Launch
echo ""
echo "========================================"
echo " Step 4: Launch"
echo "========================================"
bash "$SCRIPT_DIR/run_release.sh" --scene "$SCENE"
