#!/usr/bin/env bash
# run_release.sh — Launch Mogwai with a VisCache scene.
#
# Usage:  ./scripts/run_release.sh [--scene Bistro|Sponza|Arcade]
#
# Requires: release/ (run download_release.sh first)
#           media/ scenes (run download_scenes.sh first)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
source "$SCRIPT_DIR/version.sh" "launch" 2>/dev/null || true
RELEASE_DIR="${ROOT_DIR}/release"
MEDIA_DIR="${ROOT_DIR}/media"
REPO="ManuelKugelmann/VisCacheSketch"
SCENE="Bistro"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --scene) SCENE="$2"; shift 2 ;;
        *) echo "Usage: $0 [--scene Bistro|Sponza|Arcade]"; exit 1 ;;
    esac
done

# Deploy data files (e.g. 16RooksPattern256.txt) into release/data/
# so Falcor's AssetResolver can find them at runtime.
DATA_SRC="${ROOT_DIR}/Source/RenderPasses/ReSTIRPTPass/Data"
DATA_DST="${RELEASE_DIR}/data/ReSTIRPTPass"
if [ ! -f "$DATA_DST/16RooksPattern256.txt" ]; then
    if [ -f "$DATA_SRC/16RooksPattern256.txt" ]; then
        mkdir -p "$DATA_DST"
        cp -r "$DATA_SRC/"* "$DATA_DST/"
        echo "[launch] Deployed ReSTIRPTPass data files to release/data/"
    else
        echo "[launch] WARNING: $DATA_SRC/16RooksPattern256.txt not found in source tree"
    fi
fi
# Verify data file is present before smoke test
if [ ! -f "$DATA_DST/16RooksPattern256.txt" ]; then
    echo "[launch] WARNING: 16RooksPattern256.txt missing — ReSTIRPTPass will fail to load"
    echo "[launch] Expected at: $DATA_DST/16RooksPattern256.txt"
fi

# Smoke test
if [ -f "$RELEASE_DIR/Mogwai.exe" ]; then
    echo "[smoke] Running smoke test..."
    "$RELEASE_DIR/Mogwai.exe" --headless --script "$RELEASE_DIR/scripts/VisCache/smoke_test.py" || echo "[smoke] WARNING: Smoke test failed"
else
    echo "[launch] Mogwai.exe not found -- no release downloaded."
    echo "[launch] Run scripts/download_release.sh first, or build from source."
    echo "[launch] Releases: https://github.com/${REPO}/releases"
    exit 0
fi

# Resolve scene path
case "$SCENE" in
    Bistro)  SCENE_FILE="$MEDIA_DIR/Bistro/BistroInterior.pyscene" ;;
    Sponza)  SCENE_FILE="$MEDIA_DIR/Sponza/Sponza.pyscene" ;;
    Arcade)  SCENE_FILE="$MEDIA_DIR/Arcade/Arcade.pyscene" ;;
    *)
        echo "[launch] Unknown scene: $SCENE"
        echo "[launch] Available: Bistro, Sponza, Arcade"
        exit 1
        ;;
esac

if [ ! -f "$SCENE_FILE" ]; then
    echo "[launch] Scene file not found: $SCENE_FILE"
    echo "[launch] Run scripts/download_scenes.sh first."
    exit 1
fi

echo "[launch] Starting Mogwai with $SCENE..."
export FALCOR_MEDIA_FOLDERS="$MEDIA_DIR"
"$RELEASE_DIR/Mogwai.exe" --script "$RELEASE_DIR/scripts/VisCache/VisCache_Graph.py" --scene "$SCENE_FILE"
