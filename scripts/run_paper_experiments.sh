#!/usr/bin/env bash
# run_paper_experiments.sh — Run all captures needed for the paper.
#
# Usage:
#     ./scripts/run_paper_experiments.sh [options]
#
# Options:
#     --mogwai <path>     Path to Mogwai.exe (default: auto-detect from Falcor build)
#     --scene-dir <path>  Scene directory (default: media/)
#     --output <path>     Output root for captures (default: captures/)
#     --skip-baselines    Skip baseline captures
#     --skip-ablation     Skip ablation captures
#     --skip-reference    Skip 1024 spp reference renders
#     --skip-stress       Skip disocclusion stress test
#     --dry-run           Print commands without executing
#
# Prerequisites:
#     1. Build Falcor with VisCache plugins (./setup-build-system.sh or ./setup-build-system.bat)
#     2. Download scenes (./scripts/download_scenes.sh)
#     3. GPU with DXR 1.1 (RTX 20xx+)
#
# Outputs:
#     captures/
#       reference/          1024 spp path tracer ground truth
#       baselines/          DI/GI/PT × vanilla/local/reval/lightsel/full
#       ablation/           A–E toggles, finest/coarsest-only, no-cache
#       stress/             Disocclusion flythrough captures

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
source "$SCRIPT_DIR/version.sh" "experiments" 2>/dev/null || true

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
MOGWAI=""
SCENE_DIR="$ROOT_DIR/media"
OUTPUT_DIR="$ROOT_DIR/captures"
SKIP_BASELINES=false
SKIP_ABLATION=false
SKIP_REFERENCE=false
SKIP_STRESS=false
DRY_RUN=false

SCENES=("Bistro/BistroInterior.pyscene" "Sponza/Sponza.pyscene")

# ---------------------------------------------------------------------------
# Parse args
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --mogwai)        MOGWAI="$2"; shift 2 ;;
        --scene-dir)     SCENE_DIR="$2"; shift 2 ;;
        --output)        OUTPUT_DIR="$2"; shift 2 ;;
        --skip-baselines) SKIP_BASELINES=true; shift ;;
        --skip-ablation) SKIP_ABLATION=true; shift ;;
        --skip-reference) SKIP_REFERENCE=true; shift ;;
        --skip-stress)   SKIP_STRESS=true; shift ;;
        --dry-run)       DRY_RUN=true; shift ;;
        -h|--help)
            head -30 "$0" | tail -28
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Auto-detect Mogwai
# ---------------------------------------------------------------------------
if [ -z "$MOGWAI" ]; then
    # Try common build output locations
    for candidate in \
        "$ROOT_DIR/Falcor/build/windows-vs2022-ci/bin/Release/Mogwai.exe" \
        "$ROOT_DIR/Falcor/build/windows-ninja-msvc-ci/bin/Release/Mogwai.exe" \
        "$ROOT_DIR/Falcor/build/linux-gcc-ci/bin/Release/Mogwai" \
        "$ROOT_DIR/Falcor/build/windows-vs2022-ci/bin/Debug/Mogwai.exe" \
        ; do
        if [ -x "$candidate" ]; then
            MOGWAI="$candidate"
            break
        fi
    done
fi

if [ -z "$MOGWAI" ]; then
    echo "[run] ERROR: Mogwai not found. Build Falcor first or pass --mogwai <path>"
    exit 1
fi

echo "[run] Mogwai:    $MOGWAI"
echo "[run] Scenes:    $SCENE_DIR"
echo "[run] Output:    $OUTPUT_DIR"
echo ""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
run_mogwai() {
    local script="$1"
    local scene="$2"
    local label="$3"

    echo "[run] === $label ==="
    echo "[run] Script: $script"
    echo "[run] Scene:  $scene"

    if [ "$DRY_RUN" = true ]; then
        echo "[run] DRY RUN: $MOGWAI --headless --script $script --scene $scene"
        echo ""
        return 0
    fi

    "$MOGWAI" --headless --script "$script" --scene "$scene" 2>&1 | \
        tee "$OUTPUT_DIR/logs/${label}.log" || {
        echo "[run] WARNING: $label exited with error (code $?)"
    }
    echo ""
}

mkdir -p "$OUTPUT_DIR/logs"

# ---------------------------------------------------------------------------
# 1. Smoke test — verify plugins load
# ---------------------------------------------------------------------------
echo "[run] =========================================="
echo "[run]  Step 1: Smoke test"
echo "[run] =========================================="

if [ "$DRY_RUN" = true ]; then
    echo "[run] DRY RUN: $MOGWAI --headless --script $SCRIPT_DIR/smoke_test.py"
else
    "$MOGWAI" --headless --script "$SCRIPT_DIR/smoke_test.py" 2>&1 || {
        echo "[run] ERROR: Smoke test failed — plugins not loaded correctly"
        exit 1
    }
fi
echo ""

# ---------------------------------------------------------------------------
# 2. Reference renders (1024 spp path tracer)
# ---------------------------------------------------------------------------
if [ "$SKIP_REFERENCE" = false ]; then
    echo "[run] =========================================="
    echo "[run]  Step 2: 1024 spp reference renders"
    echo "[run] =========================================="

    for scene_rel in "${SCENES[@]}"; do
        scene_path="$SCENE_DIR/$scene_rel"
        scene_name="$(basename "$(dirname "$scene_rel")")"
        if [ ! -f "$scene_path" ]; then
            echo "[run] WARNING: $scene_path not found, skipping"
            continue
        fi
        run_mogwai "$SCRIPT_DIR/VisCache_Reference.py" "$scene_path" "reference_${scene_name}"
    done
else
    echo "[run] Skipping reference renders"
fi

# ---------------------------------------------------------------------------
# 3. Baseline captures (DI/GI/PT × configurations)
# ---------------------------------------------------------------------------
if [ "$SKIP_BASELINES" = false ]; then
    echo "[run] =========================================="
    echo "[run]  Step 3: Baseline captures (14 configs)"
    echo "[run] =========================================="

    for scene_rel in "${SCENES[@]}"; do
        scene_path="$SCENE_DIR/$scene_rel"
        scene_name="$(basename "$(dirname "$scene_rel")")"
        if [ ! -f "$scene_path" ]; then
            echo "[run] WARNING: $scene_path not found, skipping"
            continue
        fi
        run_mogwai "$SCRIPT_DIR/VisCache_Baselines.py" "$scene_path" "baselines_${scene_name}"
    done
else
    echo "[run] Skipping baseline captures"
fi

# ---------------------------------------------------------------------------
# 4. Ablation captures (10 configs)
# ---------------------------------------------------------------------------
if [ "$SKIP_ABLATION" = false ]; then
    echo "[run] =========================================="
    echo "[run]  Step 4: Ablation captures (10 configs)"
    echo "[run] =========================================="

    for scene_rel in "${SCENES[@]}"; do
        scene_path="$SCENE_DIR/$scene_rel"
        scene_name="$(basename "$(dirname "$scene_rel")")"
        if [ ! -f "$scene_path" ]; then
            echo "[run] WARNING: $scene_path not found, skipping"
            continue
        fi
        run_mogwai "$SCRIPT_DIR/VisCache_Ablation.py" "$scene_path" "ablation_${scene_name}"
    done
else
    echo "[run] Skipping ablation captures"
fi

# ---------------------------------------------------------------------------
# 5. Disocclusion stress test
# ---------------------------------------------------------------------------
if [ "$SKIP_STRESS" = false ]; then
    echo "[run] =========================================="
    echo "[run]  Step 5: Disocclusion stress test"
    echo "[run] =========================================="

    for scene_rel in "${SCENES[@]}"; do
        scene_path="$SCENE_DIR/$scene_rel"
        scene_name="$(basename "$(dirname "$scene_rel")")"
        if [ ! -f "$scene_path" ]; then
            echo "[run] WARNING: $scene_path not found, skipping"
            continue
        fi
        run_mogwai "$SCRIPT_DIR/VisCache_Stress.py" "$scene_path" "stress_${scene_name}"
    done
else
    echo "[run] Skipping stress test"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "[run] =========================================="
echo "[run]  All experiments complete"
echo "[run] =========================================="
echo ""
echo "[run] Output directory: $OUTPUT_DIR"
echo ""
echo "[run] Captured data:"
for d in "$OUTPUT_DIR"/*/; do
    [ -d "$d" ] && [ "$(basename "$d")" != "logs" ] && echo "  $(basename "$d")/"
done
echo ""
echo "[run] Logs: $OUTPUT_DIR/logs/"
echo ""
echo "[run] Next steps:"
echo "  1. Compute per-pixel MSE vs. reference (captures/reference/)"
echo "  2. Extract GPU timestamps from logs"
echo "  3. Plot convergence curves (frames to 80% hit rate)"
echo "  4. Generate paper figures (FLIP maps, timing bars)"
