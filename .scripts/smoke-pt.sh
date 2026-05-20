#!/usr/bin/env bash
# smoke-pt.sh — Validates ReSTIRPTPass baseline + VisCache-layered variant.
#
# Renders 4 frames of each on Cornell_3AreaLights. Baseline is standalone
# ReSTIRPT (no VisCache pass — GBuffer→RTXDI→ReSTIRPT→Accum→Tone).
# VisCache variant adds VisCachePass + PathTracerX shadow gating.
#
# Mirrors smoke-di.sh and smoke-nee.sh so any failure isolates to the
# specific layer (pass vs VisCache integration).
#
# Usage: .scripts/smoke-pt.sh
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

run_variant "PT baseline (no VisCache)"  "ReSTIRPT_Graph.py"
run_variant "PT + VisCache visibility"   "ReSTIRPT_VisCache_Graph.py"

echo "PASS — both ReSTIRPTPass variants render"
