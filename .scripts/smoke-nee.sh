#!/usr/bin/env bash
# smoke-nee.sh — Validates ReSTIRNEEPass K-slot + step C cascade wiring.
#
# Renders 4 frames so the K-slot atomic counter fills slots and the cell
# reservoir write→read cycle exercises. Bumps reservoirK=4 and
# cellLevelOffsetWrite=1 via Python script overrides so the smoke catches
# regressions in either the K-slot insert path or the step C multi-level
# read path (both gated to no-op at parity defaults).
#
# Usage: .scripts/smoke-nee.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Tmp script overrides the graph defaults to enable K-slot + step C.
# In source mode the harness reads from scripts/; in synced mode from
# runtime/scripts/VisCache/. Write to both so either mode works, and add
# the tmp file's name pattern to ensure git keeps it untracked.
TMP_NAME="_smoke_nee_kslot.py"
TMP_SRC="$PROJECT_ROOT/scripts/$TMP_NAME"
TMP_SYNC="$PROJECT_ROOT/runtime/scripts/VisCache/$TMP_NAME"
mkdir -p "$(dirname "$TMP_SYNC")"
trap 'rm -f "$TMP_SRC" "$TMP_SYNC"' EXIT
cat > "$TMP_SRC" <<'PY'
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ReSTIRNEEPass_Graph import render_graph_ReSTIRNEEPass
m.addGraph(render_graph_ReSTIRNEEPass(
    maxBounces=3,
    samplesPerPixel=1,
    numNEECandidates=16,
    useNEECells=True,
    cellReservoirFootprintPx=1,
    reservoirK=4,
    cellLevelOffsetWrite=1,
))
PY

cp "$TMP_SRC" "$TMP_SYNC"
OUTPUT=$("$SCRIPT_DIR/mogwai-headless.sh" "$TMP_NAME" 'CornellBox_3AreaLights.pyscene' 4 2>&1)
echo "$OUTPUT"
if echo "$OUTPUT" | grep -qF '[headless] OK'; then
    echo "PASS — NEE K-slot + step C wiring intact"
else
    echo "FAIL — NEE K-slot smoke failed; check Mogwai.exe.*.log in runtime/"
    exit 1
fi
