#!/usr/bin/env bash
# quickstart.sh — Run the full VisCacheSketch quickstart sequence (steps 0-6).
#
# Usage:  ./scripts/quickstart.sh [--scene VeachAjar|Bistro|Sponza|Arcade|CornellBox]
#                                 [--renderer viscache|restirpt|rtxdi|pathtracer|minimal]
#                                 [--variant vanilla|viscache]
#                                 [--skip-scenes] [--skip-pull] [--skip-launch] [--interactive]
#
# Steps:
#   0. git pull                   (unless --skip-pull)
#   1. download_release.sh        — download latest GitHub release (Mogwai)
#   2. download_scenes.sh         (unless --skip-scenes) — bundled scenes pre-populated from release
#   3. copy shaders/data          — copy newest .slang + data into release
#   4. run-tests.sh               — CPU algorithm tests
#   5. headless smoke test        — Mogwai --headless
#   6. launch                     — Mogwai with scene
#
# Each script is independently callable. This script just strings them together.
# Idempotent: safe to re-run. Each step skips work already done.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
source "$SCRIPT_DIR/version.sh" "quickstart" 2>/dev/null || true
SCENE="VeachAjar"
RENDERER="viscache"
VARIANT=""
INTERACTIVE=0
RELEASE_DIR="${ROOT_DIR}/release"
MEDIA_DIR="${ROOT_DIR}/release/media"
SKIP_SCENES=0
SKIP_PULL=0
SKIP_LAUNCH=0

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --scene) SCENE="$2"; shift 2 ;;
        --renderer) RENDERER="$2"; shift 2 ;;
        --variant) VARIANT="$2"; shift 2 ;;
        --skip-scenes) SKIP_SCENES=1; shift ;;
        --skip-pull) SKIP_PULL=1; shift ;;
        --skip-launch) SKIP_LAUNCH=1; shift ;;
        --interactive|-i) INTERACTIVE=1; shift ;;
        *) echo "Usage: $0 [--scene ...] [--renderer ...] [--variant vanilla|viscache] [--skip-scenes] [--skip-pull] [--skip-launch] [--interactive]"; exit 1 ;;
    esac
done

# Interactive selection
if [ "$INTERACTIVE" -eq 1 ]; then
    echo ""
    echo "========================================"
    echo " VisCacheSketch — Interactive Setup"
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

    # Ask variant for all renderers except viscache (already includes VisCache)
    if [[ "$RENDERER" != "viscache" ]]; then
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

# Select graph script based on renderer
case "$RENDERER" in
    viscache)    GRAPH_SCRIPT="VisCache_Graph.py" ;;
    minimal)     GRAPH_SCRIPT="MinimalPathTracer_Graph.py" ;;
    pathtracer)  GRAPH_SCRIPT="PathTracer_Graph.py" ;;
    rtxdi)       GRAPH_SCRIPT="RTXDI_Graph.py" ;;
    restirpt)    GRAPH_SCRIPT="ReSTIRPT_Graph.py" ;;
    *)
        echo "[quickstart] Unknown renderer: $RENDERER"
        echo "[quickstart] Available: viscache, restirpt, rtxdi, pathtracer, minimal"
        echo "[quickstart] Add --variant viscache to enable visibility cache with any renderer"
        exit 1
        ;;
esac

# Apply --variant viscache: switch to per-renderer VisCache graph
if [ "$VARIANT" = "viscache" ]; then
    case "$RENDERER" in
        minimal)     GRAPH_SCRIPT="MinimalPathTracer_VisCache_Graph.py" ;;
        pathtracer)  GRAPH_SCRIPT="PathTracer_VisCache_Graph.py" ;;
        rtxdi)       GRAPH_SCRIPT="RTXDI_VisCache_Graph.py" ;;
        restirpt)    GRAPH_SCRIPT="VisCache_Graph.py" ;;
    esac
fi

# ---------------------------------------------------------------------------
# Step 0: Pull latest
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo " Step 0: Pull latest changes"
echo "========================================"
if [ "$SKIP_PULL" -eq 1 ]; then
    echo "[quickstart] step 0 pull -- skipped (--skip-pull)"
else
    BRANCH=$(git -C "$ROOT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || true)
    if [ -n "$BRANCH" ]; then
        echo "[quickstart] step 0 pull (branch: $BRANCH)"
        # Stash local changes so pull does not fail
        git -C "$ROOT_DIR" stash --quiet 2>/dev/null || true
        git -C "$ROOT_DIR" pull origin "$BRANCH" || echo "[quickstart] WARNING: pull failed, continuing with current checkout"
        # Re-apply stashed changes (if any)
        git -C "$ROOT_DIR" stash pop --quiet 2>/dev/null || true
    else
        echo "[quickstart] step 0 pull -- skipped (not a git repo)"
    fi
fi

# ---------------------------------------------------------------------------
# Step 1: Download release
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo " Step 1: Download latest release"
echo "========================================"
echo "[quickstart] step 1 download release"
bash "$SCRIPT_DIR/download_release.sh"

# ---------------------------------------------------------------------------
# Step 2: Download scenes (bundled scenes pre-populated from release)
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo " Step 2: Download test scenes"
echo "========================================"
if [ "$SKIP_SCENES" -eq 1 ]; then
    echo "[quickstart] step 2 download scenes -- skipped (--skip-scenes)"
else
    echo "[quickstart] step 2 download scenes"
    bash "$SCRIPT_DIR/download_scenes.sh" || echo "[quickstart] WARNING: Some scenes failed to download"
fi

# ---------------------------------------------------------------------------
# Step 3: Copy newer shaders, data, etc. to release
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo " Step 3: Copy newer shaders, data, etc. to release"
echo "========================================"
if [ -d "$RELEASE_DIR" ]; then
    echo "[quickstart] step 3 deploy shaders, scripts, data from source tree to release"

    # ---- Deploy ALL .slang shaders (source tree is authoritative) ----
    # Force-copy (not date-based) — git pull/checkout timestamps are unreliable.

    # Falcor built-in shaders: Falcor/Source/Falcor/**/*.slang → release/shaders/
    FALCOR_SRC="${ROOT_DIR}/Falcor/Source/Falcor"
    if [ -d "$FALCOR_SRC" ]; then
        find "$FALCOR_SRC" -name "*.slang" -print0 | while IFS= read -r -d '' src; do
            rel="${src#$FALCOR_SRC/}"
            dst="${RELEASE_DIR}/shaders/${rel}"
            mkdir -p "$(dirname "$dst")"
            cp -f "$src" "$dst"
        done
        echo "[quickstart]   Falcor built-in shaders deployed"
    fi

    # Custom render pass shaders
    for pass in VisCache ReSTIRPTPass; do
        PASS_SRC="${ROOT_DIR}/Source/RenderPasses/${pass}"
        PASS_DST="${RELEASE_DIR}/shaders/RenderPasses/${pass}"
        if [ -d "$PASS_SRC" ]; then
            mkdir -p "$PASS_DST"
            find "$PASS_SRC" -name "*.slang" -exec cp -f {} "$PASS_DST/" \;
            echo "[quickstart]   ${pass} shaders deployed"
        fi
    done

    # ---- Deploy scripts ----
    SCRIPTS_SRC="${ROOT_DIR}/scripts"
    SCRIPTS_DST="${RELEASE_DIR}/scripts/VisCache"
    if [ -f "$SCRIPTS_SRC/smoke_test.py" ]; then
        mkdir -p "$SCRIPTS_DST"
        cp -r "$SCRIPTS_SRC/"* "$SCRIPTS_DST/"
        echo "[quickstart]   scripts deployed"
    fi

    # ---- Deploy ReSTIRPTPass data files ----
    DATA_SRC="${ROOT_DIR}/Source/RenderPasses/ReSTIRPTPass/Data"
    DATA_DST="${RELEASE_DIR}/data/ReSTIRPTPass"
    if [ -f "$DATA_SRC/16RooksPattern256.txt" ]; then
        mkdir -p "$DATA_DST"
        cp -r "$DATA_SRC/"* "$DATA_DST/"
        echo "[quickstart]   ReSTIRPTPass data deployed"
    fi

    # ---- Validate NRD (denoiser) availability in release ----
    NRD_OK=1
    if [ ! -f "$RELEASE_DIR/NRDPass.dll" ]; then
        echo "[quickstart]   NRDPass.dll: MISSING"
        NRD_OK=0
    else
        echo "[quickstart]   NRDPass.dll: OK"
    fi
    if [ ! -f "$RELEASE_DIR/NRD.dll" ]; then
        echo "[quickstart]   NRD.dll: MISSING"
        NRD_OK=0
    else
        echo "[quickstart]   NRD.dll: OK"
    fi
    if [ "$NRD_OK" -eq 0 ]; then
        echo "[quickstart]   WARNING: NRD denoiser not in release -- output will be raw noisy radiance."
        echo "[quickstart]   Rebuild with D3D12 + packman NRD package, or download a release that includes NRD."
    else
        echo "[quickstart]   NRD denoiser: available"
    fi

    # ---- Validate shaders (content hash) ----
    PYTHON_CMD=""
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_CMD="python3"
    elif command -v python >/dev/null 2>&1; then
        PYTHON_CMD="python"
    fi
    if [ -n "$PYTHON_CMD" ]; then
        "$PYTHON_CMD" "${ROOT_DIR}/scripts/validate_shaders.py" --root-dir "${ROOT_DIR}" --release-dir "${RELEASE_DIR}" || \
            echo "[quickstart] WARNING: Shader validation found issues (see above)"
    else
        echo "[quickstart] python not found -- skipping shader content validation"
    fi
else
    echo "[quickstart] step 3 deploy shaders, scripts, data -- skipped (no release found)"
fi

# ---------------------------------------------------------------------------
# Step 4: Run Python tests
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo " Step 4: Run Python tests"
echo "========================================"
echo "[quickstart] step 4 run py tests"
bash "$SCRIPT_DIR/run-tests.sh" || echo "[quickstart] WARNING: Some tests failed"

# ---------------------------------------------------------------------------
# Step 5: Run headless smoke test (requires GPU — skip on CI)
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo " Step 5: Headless smoke test"
echo "========================================"
if [ "$SKIP_LAUNCH" -eq 1 ]; then
    echo "[quickstart] step 5 headless smoke test -- skipped (--skip-launch)"
elif [ -f "$RELEASE_DIR/Mogwai.exe" ]; then
    echo "[quickstart] step 5 run headless smoke test"
    "$RELEASE_DIR/Mogwai.exe" --headless --script "$RELEASE_DIR/scripts/VisCache/smoke_test.py" || \
        echo "[quickstart] WARNING: Smoke test failed"
else
    echo "[quickstart] step 5 headless smoke test -- skipped (Mogwai.exe not found)"
fi

# ---------------------------------------------------------------------------
# Step 6: Launch (requires GPU — skip on CI)
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo " Step 6: Launch"
echo "========================================"
if [ "$SKIP_LAUNCH" -eq 1 ]; then
    echo "[quickstart] step 6 launch -- skipped (--skip-launch)"
    exit 0
fi

if [ ! -f "$RELEASE_DIR/Mogwai.exe" ]; then
    echo "[quickstart] step 6 launch -- skipped (Mogwai.exe not found)"
    echo "[quickstart] Run scripts/download_release.sh first, or build from source."
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
        echo "[quickstart] step 6 launch -- skipped (unknown scene: $SCENE)"
        exit 0
        ;;
esac

if [ ! -f "$SCENE_FILE" ]; then
    echo "[quickstart] step 6 launch -- skipped (scene file not found: $SCENE_FILE)"
    echo "[quickstart] Run scripts/download_scenes.sh first."
    exit 0
fi

# Show checkout vs release commit SHA + timestamp for diagnostics
CHECKOUT_SHA=$(git -C "$ROOT_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
CHECKOUT_DATE=$(git -C "$ROOT_DIR" log -1 --format=%ci 2>/dev/null || echo "unknown")
RELEASE_SHA="unknown"
RELEASE_VER="unknown"
if [ -f "$RELEASE_DIR/.release-sha" ]; then
    RELEASE_SHA=$(head -c 7 "$RELEASE_DIR/.release-sha")
fi
if [ -f "$RELEASE_DIR/.release-version" ]; then
    RELEASE_VER=$(cat "$RELEASE_DIR/.release-version")
fi
echo "[quickstart] checkout: $CHECKOUT_SHA ($CHECKOUT_DATE)"
echo "[quickstart] release:  $RELEASE_SHA ($RELEASE_VER)"
if [ "$CHECKOUT_SHA" != "unknown" ] && [ "$RELEASE_SHA" != "unknown" ]; then
    if [ "$CHECKOUT_SHA" != "$RELEASE_SHA" ]; then
        echo "[quickstart] WARNING: checkout and release are from different commits -- shader/binary mismatch possible"
    fi
fi

SCRIPT_PATH="$RELEASE_DIR/scripts/VisCache/$GRAPH_SCRIPT"
if [ ! -f "$SCRIPT_PATH" ]; then
    echo "[quickstart] ERROR: Graph script not found: $SCRIPT_PATH"
    echo "[quickstart] Check that scripts were deployed to release/scripts/VisCache/"
    exit 1
fi

echo "[quickstart] step 6 launch ($SCENE, renderer: $RENDERER)"
echo "[quickstart] $RELEASE_DIR/Mogwai.exe --script scripts/VisCache/$GRAPH_SCRIPT --scene $SCENE_FILE"
echo ""
export FALCOR_MEDIA_FOLDERS="$MEDIA_DIR"
"$RELEASE_DIR/Mogwai.exe" --script "$SCRIPT_PATH" --scene "$SCENE_FILE"
