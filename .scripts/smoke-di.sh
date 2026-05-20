#!/usr/bin/env bash
# smoke-di.sh — Validates ReSTIRDIPass baseline + VisCache-layered variant.
#
# Renders 4 frames of each on Cornell_3AreaLights so the cell pool fills
# and DI reservoirs reach a representative steady state. Both variants
# share the same DI pass; only the VisCache visibility/light-selection
# toggles differ — failure of one but not the other points at the
# VisCache integration layer, not the DI pass itself.
#
# Usage: .scripts/smoke-di.sh
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

run_variant "DI baseline (vblind)"      "ReSTIRDIPass_Graph.py"
run_variant "DI + VisCache visibility"  "ReSTIRDIPass_VisCache_Graph.py"

echo "PASS — both ReSTIRDIPass variants render"
