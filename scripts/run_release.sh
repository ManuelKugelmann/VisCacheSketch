#!/usr/bin/env bash
# run_release.sh — Launch Mogwai with a VisCache scene.
#
# Usage:  ./scripts/run_release.sh [--scene VeachAjar|Bistro|Sponza|Arcade|CornellBox]
#                                  [--renderer viscache|minimal]
#
# Requires: release/ (run download_release.sh first)
#           media/ scenes (run download_scenes.sh first)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
source "$SCRIPT_DIR/version.sh" "launch" 2>/dev/null || true
RELEASE_DIR="${ROOT_DIR}/release"
MEDIA_DIR="${ROOT_DIR}/release/media"
REPO="ManuelKugelmann/VisCacheSketch"
SCENE="VeachAjar"
RENDERER="viscache"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --scene) SCENE="$2"; shift 2 ;;
        --renderer) RENDERER="$2"; shift 2 ;;
        *) echo "Usage: $0 [--scene VeachAjar|Bistro|Sponza|Arcade|CornellBox] [--renderer viscache|minimal]"; exit 1 ;;
    esac
done

# Select graph script based on renderer
case "$RENDERER" in
    viscache) GRAPH_SCRIPT="VisCache_Graph.py" ;;
    minimal)  GRAPH_SCRIPT="MinimalPathTracer_Graph.py" ;;
    *)
        echo "[launch] Unknown renderer: $RENDERER"
        echo "[launch] Available: viscache, minimal"
        exit 1
        ;;
esac

# Deploy fresh scripts from source tree into release/scripts/VisCache/
# so the release always uses up-to-date graph configs and smoke tests.
SCRIPTS_SRC="${ROOT_DIR}/scripts"
SCRIPTS_DST="${RELEASE_DIR}/scripts/VisCache"
if [ -f "$SCRIPTS_SRC/smoke_test.py" ]; then
    mkdir -p "$SCRIPTS_DST"
    cp -r "$SCRIPTS_SRC/"* "$SCRIPTS_DST/"
    echo "[launch] Deployed fresh scripts from source tree to release/scripts/VisCache/"
fi

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

# Deploy shaders from source tree (source is always authoritative)
# Force-copy all .slang from source → release/shaders/ so deployed shaders
# always match the current checkout.  Git timestamps are unreliable.
FALCOR_SRC="${ROOT_DIR}/Falcor/Source/Falcor"
if [ -d "$FALCOR_SRC" ]; then
    find "$FALCOR_SRC" -name "*.slang" -print0 | while IFS= read -r -d '' src; do
        rel="${src#$FALCOR_SRC/}"
        dst="${RELEASE_DIR}/shaders/${rel}"
        mkdir -p "$(dirname "$dst")"
        cp -f "$src" "$dst"
    done
fi
for pass in VisCache ReSTIRPTPass; do
    PASS_SRC="${ROOT_DIR}/Source/RenderPasses/${pass}"
    PASS_DST="${RELEASE_DIR}/shaders/RenderPasses/${pass}"
    if [ -d "$PASS_SRC" ]; then
        mkdir -p "$PASS_DST"
        find "$PASS_SRC" -name "*.slang" -exec cp -f {} "$PASS_DST/" \;
    fi
done
echo "[launch] Shaders deployed from source tree"

# Validate (diagnostic — catch wrong locations, partial copies, etc.)
if command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1; then
    PYTHON_CMD=$(command -v python3 || command -v python)
    "$PYTHON_CMD" "${ROOT_DIR}/scripts/validate_shaders.py" --root-dir "${ROOT_DIR}" --release-dir "${RELEASE_DIR}" || \
        echo "[launch] WARNING: Shader validation found issues — see above"
else
    # Fallback: at least check sentinel
    if [ ! -f "${RELEASE_DIR}/shaders/Scene/Material/TextureSampler.slang" ]; then
        echo "[launch] ERROR: Falcor shaders missing from release/shaders/ after deploy"
        exit 1
    fi
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
    VeachAjar)  SCENE_FILE="$RELEASE_DIR/data/ReSTIRPTPass/VeachAjar/VeachAjar.pyscene" ;;
    Bistro)     SCENE_FILE="$MEDIA_DIR/Bistro/BistroInterior.pyscene" ;;
    Sponza)     SCENE_FILE="$MEDIA_DIR/Sponza/Sponza.pyscene" ;;
    Arcade)     SCENE_FILE="$MEDIA_DIR/Arcade/Arcade.pyscene" ;;
    CornellBox) SCENE_FILE="$ROOT_DIR/scenes/CornellBox.pyscene" ;;
    *)
        echo "[launch] Unknown scene: $SCENE"
        echo "[launch] Available: VeachAjar, Bistro, Sponza, Arcade, CornellBox"
        exit 1
        ;;
esac

if [ ! -f "$SCENE_FILE" ]; then
    echo "[launch] Scene file not found: $SCENE_FILE"
    echo "[launch] Run scripts/download_scenes.sh first."
    exit 1
fi

echo "[launch] Starting Mogwai with $SCENE (renderer: $RENDERER)..."
export FALCOR_MEDIA_FOLDERS="$MEDIA_DIR"
"$RELEASE_DIR/Mogwai.exe" --script "$RELEASE_DIR/scripts/VisCache/$GRAPH_SCRIPT" --scene "$SCENE_FILE"
