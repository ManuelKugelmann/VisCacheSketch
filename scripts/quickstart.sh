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
RENDERER="restirpt"
VARIANT=""
INTERACTIVE=0
RUNTIME_DIR="${ROOT_DIR}/runtime"
MEDIA_DIR="${ROOT_DIR}/runtime/media"
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
    echo ""
    read -rp "  Choice [1-4, default=4]: " RCHOICE
    RCHOICE="${RCHOICE:-4}"
    case "$RCHOICE" in
        1) RENDERER="minimal" ;;
        2) RENDERER="pathtracer" ;;
        3) RENDERER="rtxdi" ;;
        4) RENDERER="restirpt" ;;
    esac

    # Ask variant
    if true; then
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
if [ -d "$RUNTIME_DIR" ]; then
    echo "[quickstart] step 3 sync shaders, scripts, data from source tree to release"
    bash "${ROOT_DIR}/.scripts/sync_to_runtime.sh"
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
elif [ -f "$RUNTIME_DIR/Mogwai.exe" ]; then
    echo "[quickstart] step 5 run headless smoke test"
    "$RUNTIME_DIR/Mogwai.exe" --headless --script "$RUNTIME_DIR/scripts/VisCache/SmokeTest.py" || \
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

if [ ! -f "$RUNTIME_DIR/Mogwai.exe" ]; then
    echo "[quickstart] step 6 launch -- skipped (Mogwai.exe not found)"
    echo "[quickstart] Run scripts/download_release.sh first, or build from source."
    exit 0
fi

# Show checkout vs release commit SHA + timestamp for diagnostics
CHECKOUT_SHA=$(git -C "$ROOT_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
CHECKOUT_DATE=$(git -C "$ROOT_DIR" log -1 --format=%ci 2>/dev/null || echo "unknown")
RELEASE_SHA="unknown"
RELEASE_VER="unknown"
if [ -f "$RUNTIME_DIR/.release-sha" ]; then
    RELEASE_SHA=$(head -c 7 "$RUNTIME_DIR/.release-sha")
fi
if [ -f "$RUNTIME_DIR/.release-version" ]; then
    RELEASE_VER=$(cat "$RUNTIME_DIR/.release-version")
fi
echo "[quickstart] checkout: $CHECKOUT_SHA ($CHECKOUT_DATE)"
echo "[quickstart] release:  $RELEASE_SHA ($RELEASE_VER)"
if [ "$CHECKOUT_SHA" != "unknown" ] && [ "$RELEASE_SHA" != "unknown" ]; then
    if [ "$CHECKOUT_SHA" != "$RELEASE_SHA" ]; then
        echo "[quickstart] WARNING: checkout and release are from different commits -- shader/binary mismatch possible"
    fi
fi

# Delegate to run_release.sh
echo "[quickstart] step 6 launch ($SCENE, renderer: $RENDERER)"
LAUNCH_ARGS="--scene $SCENE --renderer $RENDERER"
[ -n "$VARIANT" ] && LAUNCH_ARGS="$LAUNCH_ARGS --variant $VARIANT"
# shellcheck disable=SC2086
bash "$SCRIPT_DIR/run_release.sh" $LAUNCH_ARGS
