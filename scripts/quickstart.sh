#!/usr/bin/env bash
# quickstart.sh — Run the full VisCacheSketch quickstart sequence.
#
# Usage:  ./scripts/quickstart.sh [--scene VeachAjar|Bistro|Sponza|Arcade|CornellBox]
#                                 [--renderer viscache|restirpt|rtxdi|pathtracer|minimal]
#                                 [--skip-scenes] [--interactive]
#
# Calls each step in order:
#   1. download_release.sh  — download latest GitHub release
#   2. download_scenes.sh   — fetch test scenes (unless --skip-scenes) — bundled scenes pre-populated from release
#   3. run-tests.sh         — CPU algorithm tests
#   4. run_release.sh       — smoke test + launch Mogwai
#
# Each script is independently callable. This script just strings them together.
# Idempotent: safe to re-run. Each step skips work already done.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCENE="VeachAjar"
RENDERER="viscache"
VARIANT=""
INTERACTIVE=0

# shellcheck disable=SC1091
source "$SCRIPT_DIR/version.sh" "quickstart" 2>/dev/null || true
SKIP_SCENES=0

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --scene) SCENE="$2"; shift 2 ;;
        --renderer) RENDERER="$2"; shift 2 ;;
        --variant) VARIANT="$2"; shift 2 ;;
        --skip-scenes) SKIP_SCENES=1; shift ;;
        --interactive|-i) INTERACTIVE=1; shift ;;
        *) echo "Usage: $0 [--scene ...] [--renderer ...] [--variant vanilla|viscache] [--skip-scenes] [--interactive]"; exit 1 ;;
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

# 1. Download release
echo ""
echo "========================================"
echo " Step 1: Download latest release"
echo "========================================"
bash "$SCRIPT_DIR/download_release.sh"

# 2. Download scenes (bundled scenes pre-populated from release)
if [ "$SKIP_SCENES" -eq 1 ]; then
    echo "[quickstart] Skipping scene download (--skip-scenes)"
else
    echo ""
    echo "========================================"
    echo " Step 2: Download test scenes"
    echo "========================================"
    bash "$SCRIPT_DIR/download_scenes.sh" || echo "[quickstart] WARNING: Some scenes failed to download"
fi

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
bash "$SCRIPT_DIR/run_release.sh" --scene "$SCENE" --renderer "$RENDERER"
