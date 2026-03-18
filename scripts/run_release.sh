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
RUNTIME_DIR="${ROOT_DIR}/runtime"
MEDIA_DIR="${ROOT_DIR}/runtime/media"
REPO="ManuelKugelmann/VisCacheSketch"
SCENE="VeachAjar"
RENDERER="restirpt"
VARIANT=""
# Default to interactive when no arguments given
if [ $# -eq 0 ]; then INTERACTIVE=1; else INTERACTIVE=0; fi

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
    echo ""
    read -rp "  Choice [1-4, default=4]: " RCHOICE
    RCHOICE="${RCHOICE:-4}"
    case "$RCHOICE" in
        1) RENDERER="minimal" ;;
        2) RENDERER="pathtracer" ;;
        3) RENDERER="rtxdi" ;;
        4) RENDERER="restirpt" ;;
    esac

    echo ""
    echo "  Select variant:"
    echo "    1. Vanilla   — no visibility cache"
    echo "    2. VisCache  — with visibility cache"
    echo ""
    read -rp "  Choice [1-2, default=1]: " VCHOICE
    VCHOICE="${VCHOICE:-1}"
    case "$VCHOICE" in
        1) VARIANT="vanilla" ;;
        2) RENDERER="restirpt"; VARIANT="" ;;
    esac

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

# Select graph script based on renderer
case "$RENDERER" in
    minimal)     GRAPH_SCRIPT="MinimalPathTracer_Graph.py" ;;
    pathtracer)  GRAPH_SCRIPT="PathTracer_Graph.py" ;;
    rtxdi)       GRAPH_SCRIPT="RTXDI_Graph.py" ;;
    restirpt)    GRAPH_SCRIPT="ReSTIRPT_Graph.py" ;;
    *)
        echo "[launch] Unknown renderer: $RENDERER"
        echo "[launch] Available: restirpt, rtxdi, pathtracer, minimal"
        echo "[launch] Add --variant viscache to enable visibility cache"
        exit 1
        ;;
esac

# Apply --variant viscache: switch to per-renderer VisCache graph
if [ "$VARIANT" = "viscache" ]; then
    case "$RENDERER" in
        minimal)     GRAPH_SCRIPT="MinimalPathTracer_VisCache_Graph.py" ;;
        pathtracer)  GRAPH_SCRIPT="PathTracer_VisCache_Graph.py" ;;
        rtxdi)       GRAPH_SCRIPT="RTXDI_VisCache_Graph.py" ;;
        restirpt)    GRAPH_SCRIPT="ReSTIRPT_VisCache_Graph.py" ;;
    esac
fi

# ---------------------------------------------------------------------------
# Sync shaders, scripts, data from source to release/
# ---------------------------------------------------------------------------
bash "${ROOT_DIR}/.scripts/sync_to_runtime.sh"

# ---------------------------------------------------------------------------
# Check Mogwai.exe exists
# ---------------------------------------------------------------------------
if [ ! -f "$RUNTIME_DIR/Mogwai.exe" ]; then
    echo "[launch] Mogwai.exe not found -- no release downloaded."
    echo "[launch] Run scripts/download_release.sh first, or build from source."
    echo "[launch] Releases: https://github.com/${REPO}/releases"
    exit 0
fi

# Resolve scene path
case "$SCENE" in
    VeachAjar)  SCENE_FILE="$RUNTIME_DIR/data/ReSTIRPTPass/VeachAjar/VeachAjar.pyscene" ;;
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

SCRIPT_PATH="$RUNTIME_DIR/scripts/VisCache/$GRAPH_SCRIPT"
if [ ! -f "$SCRIPT_PATH" ]; then
    echo "[launch] ERROR: Graph script not found: $SCRIPT_PATH"
    echo "[launch] Check that scripts were deployed to release/scripts/VisCache/"
    exit 1
fi

echo "[launch] Starting Mogwai with $SCENE (renderer: $RENDERER)..."
export FALCOR_MEDIA_FOLDERS="$MEDIA_DIR"
"$RUNTIME_DIR/Mogwai.exe" --script "$SCRIPT_PATH" --scene "$SCENE_FILE"
