#!/usr/bin/env bash
# mogwai-headless.sh — Run Mogwai headless from anywhere (handles cd to release/).
#
# Usage: .scripts/mogwai-headless.sh <Graph-pattern> [scene.pyscene] [frames]
#   Graph:  graph script name or glob pattern (matched in scripts/VisCache/)
#           e.g. "MinimalPathTracer_Graph.py" or "*_Graph.py" or "*VisCache*"
#   Scene:  scene path relative to release/ (default: VeachAjar)
#   Frames: number of frames to render (default: 2)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RELEASE="$ROOT/release"

PATTERN="${1:?Usage: mogwai-headless.sh <Graph-pattern> [scene] [frames]}"
SCENE="${2:-data/ReSTIRPTPass/VeachAjar/VeachAjar.pyscene}"
FRAMES="${3:-2}"

cd "$RELEASE"

# Expand glob pattern against scripts/VisCache/
shopt -s nullglob
MATCHES=(scripts/VisCache/$PATTERN)
shopt -u nullglob

if [ ${#MATCHES[@]} -eq 0 ]; then
    echo "No scripts matched pattern: $PATTERN"
    exit 1
fi

PASS=0
FAIL=0

for SCRIPT in "${MATCHES[@]}"; do
    NAME="$(basename "$SCRIPT")"
    echo "=== Testing: $NAME ==="
    if GRAPH_SCRIPT="$SCRIPT" SCENE_FILE="$SCENE" NUM_FRAMES="$FRAMES" \
        ./Mogwai.exe --headless \
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
