#!/usr/bin/env bash
# mogwai-headless.sh — Run Mogwai headless from anywhere (handles cd to runtime/).
#
# Usage: .scripts/mogwai-headless.sh <Graph-pattern> [scene.pyscene] [frames]
#   Graph:  graph script name or glob pattern (matched in scripts/VisCache/)
#           e.g. "MinimalPathTracer_Graph.py" or "*_Graph.py" or "*VisCache*"
#   Scene:  scene path relative to runtime/ (default: CornellBox)
#   Frames: number of frames to render (default: 2)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNTIME="$PROJECT_ROOT/runtime"

PATTERN="${1:?Usage: mogwai-headless.sh <Graph-pattern> [scene] [frames]}"
SCENE="${2:-media/scenes/CornellBox_1AreaLight.pyscene}"
FRAMES="${3:-2}"

cd "$RUNTIME"

# Expand glob pattern against scripts/VisCache/
shopt -s nullglob
MATCHES=("$RUNTIME/scripts/VisCache/"$PATTERN)
shopt -u nullglob

if [ ${#MATCHES[@]} -eq 0 ]; then
    echo "No scripts matched pattern: $PATTERN"
    exit 1
fi

PASS=0
FAIL=0

for MATCH in "${MATCHES[@]}"; do
    SCRIPT="${MATCH#$RUNTIME/}"
    NAME="$(basename "$SCRIPT")"
    echo "=== Testing: $NAME ==="
    if GRAPH_SCRIPT="$SCRIPT" SCENE_FILE="$SCENE" NUM_FRAMES="$FRAMES" \
        "$RUNTIME/Mogwai.exe" --headless \
        --script "scripts/VisCache/run_graph_headless.py" 2>&1; then
        echo "=== PASS: $NAME ==="
        PASS=$((PASS + 1))
    else
        echo "=== FAIL: $NAME ==="
        FAIL=$((FAIL + 1))
    fi
    echo ""
done

echo "Results: $PASS passed, $FAIL failed (out of ${#MATCHES[@]} scripts)"
[ $FAIL -eq 0 ]
