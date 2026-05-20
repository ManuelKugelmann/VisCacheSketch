#!/usr/bin/env bash
# smoke-nee.sh — Validates ReSTIRNEEPass baseline + VisCache-layered variant.
#
# Renders 4 frames of each on Cornell_3AreaLights so the K-slot atomic
# counter fills, cell reservoirs warm up, and the path-cumulative
# Fibonacci footprint exercises. Both variants share the same NEE pass;
# only the VisCache visibility/light-selection toggles + useNEECells
# differ — failure of one but not the other points at the VisCache
# integration layer, not the NEE pass itself.
#
# Usage: .scripts/smoke-nee.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRAMES=4
SCENE='CornellBox_3AreaLights.pyscene'

run_variant() {
    local label="$1"
    local script="$2"
    echo "--- $label ($script) ---"
    OUTPUT=$("$SCRIPT_DIR/mogwai-headless.sh" "$script" "$SCENE" "$FRAMES" 2>&1)
    if echo "$OUTPUT" | grep -qF '[headless] OK'; then
        echo "PASS — $label"
    else
        echo "$OUTPUT"
        echo "FAIL — $label; check Mogwai.exe.*.log in runtime/"
        exit 1
    fi
}

# Drops the previous K-slot+stepC-specific tmp script (kept as a regression
# probe only for the K-slot wiring). The wiring is exercised through the
# main K-slot ladder steps; this smoke now mirrors smoke-di.sh and tests
# both the vblind baseline and the VisCache-layered variant.
run_variant "NEE baseline (vblind)"      "ReSTIRNEEPass_Graph.py"
run_variant "NEE + VisCache visibility"  "ReSTIRNEEPass_VisCache_Graph.py"

echo "PASS — both ReSTIRNEEPass variants render"
