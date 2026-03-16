#!/usr/bin/env bash
# run_release.sh — Launch Mogwai with a VisCache scene.
#
# Usage:  ./scripts/run_release.sh [--scene VeachAjar|Bistro|Sponza|Arcade|CornellBox]
#                                  [--renderer viscache|restirpt|rtxdi|pathtracer|minimal]
#                                  [--variant vanilla|viscache] [--interactive]
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
VARIANT=""
INTERACTIVE=0

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --scene) SCENE="$2"; shift 2 ;;
        --renderer) RENDERER="$2"; shift 2 ;;
        --variant) VARIANT="$2"; shift 2 ;;
        --interactive|-i) INTERACTIVE=1; shift ;;
        *) echo "Usage: $0 [--scene ...] [--renderer ...] [--variant vanilla|viscache] [--interactive]"; exit 1 ;;
    esac
done

# Interactive selection
if [ "$INTERACTIVE" -eq 1 ]; then
    echo ""
    echo "========================================"
    echo " VisCacheSketch — Interactive Launch"
    echo "========================================"
    echo ""
    echo "  Select renderer:"
    echo "    1. MinimalPathTracer  — lightweight, progressive accumulation"
    echo "    2. PathTracer         — full Falcor path tracer (NEE, MIS, volumes)"
    echo "    3. RTXDI              — ReSTIR DI direct lighting only"
    echo "    4. ReSTIR PT          — ReSTIR path tracing (indirect + direct)"
    echo "    5. VisCache           — full VisCache pipeline (ReSTIR PT + visibility cache)"
    echo ""
    read -rp "  Choice [1-5, default=5]: " RCHOICE
    RCHOICE="${RCHOICE:-5}"
    case "$RCHOICE" in
        1) RENDERER="minimal" ;;
        2) RENDERER="pathtracer" ;;
        3) RENDERER="rtxdi" ;;
        4) RENDERER="restirpt" ;;
        5) RENDERER="viscache" ;;
    esac

    # Ask variant for renderers that support VisCache (all except minimal/viscache)
    if [[ "$RENDERER" != "minimal" && "$RENDERER" != "viscache" ]]; then
        echo ""
        echo "  Select variant:"
        echo "    1. Vanilla   — no visibility cache"
        echo "    2. VisCache  — with visibility cache"
        echo ""
        read -rp "  Choice [1-2, default=1]: " VCHOICE
        VCHOICE="${VCHOICE:-1}"
        case "$VCHOICE" in
            1) VARIANT="vanilla" ;;
            2) RENDERER="viscache"; VARIANT="" ;;
        esac
    fi

    echo ""
    echo "  Select scene:"
    echo "    1. VeachAjar   — small test scene (no download needed)"
    echo "    2. Bistro      — restaurant interior (~3.2 GB download)"
    echo "    3. Sponza      — classic atrium (~70 MB download)"
    echo "    4. Arcade      — game arcade (bundled with release)"
    echo "    5. CornellBox  — simple box scene"
    echo ""
    read -rp "  Choice [1-5, default=1]: " SCHOICE
    SCHOICE="${SCHOICE:-1}"
    case "$SCHOICE" in
        1) SCENE="VeachAjar" ;;
        2) SCENE="Bistro" ;;
        3) SCENE="Sponza" ;;
        4) SCENE="Arcade" ;;
        5) SCENE="CornellBox" ;;
    esac

    echo ""
    echo "  Selected: renderer=$RENDERER, scene=$SCENE"
    [ -n "$VARIANT" ] && echo "  Variant: $VARIANT"
    echo ""
fi

# Apply --variant: viscache overrides to full VisCache pipeline
if [[ "$VARIANT" == "viscache" && "$RENDERER" != "minimal" ]]; then
    RENDERER="viscache"
fi

# Select graph script based on renderer
case "$RENDERER" in
    viscache)    GRAPH_SCRIPT="VisCache_Graph.py" ;;
    minimal)     GRAPH_SCRIPT="MinimalPathTracer_Graph.py" ;;
    pathtracer)  GRAPH_SCRIPT="PathTracer_Graph.py" ;;
    rtxdi)       GRAPH_SCRIPT="RTXDI_Graph.py" ;;
    restirpt)    GRAPH_SCRIPT="ReSTIRPT_Graph.py" ;;
    *)
        echo "[launch] Unknown renderer: $RENDERER"
        echo "[launch] Available: viscache, restirpt, rtxdi, pathtracer, minimal"
        echo "[launch] Add --variant viscache to enable visibility cache with any renderer"
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

SCRIPT_PATH="$RELEASE_DIR/scripts/VisCache/$GRAPH_SCRIPT"
if [ ! -f "$SCRIPT_PATH" ]; then
    echo "[launch] ERROR: Graph script not found: $SCRIPT_PATH"
    echo "[launch] Check that scripts were deployed to release/scripts/VisCache/"
    exit 1
fi

echo "[launch] Starting Mogwai with $SCENE (renderer: $RENDERER)..."
export FALCOR_MEDIA_FOLDERS="$MEDIA_DIR"
"$RELEASE_DIR/Mogwai.exe" --script "$SCRIPT_PATH" --scene "$SCENE_FILE"
