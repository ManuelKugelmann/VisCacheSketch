#!/usr/bin/env bash
# smoke.sh — Quick build validation: load one graph, render 1 frame with scene.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RELEASE="$(cd "$SCRIPT_DIR/.." && pwd)/release"

cd "$RELEASE"
GRAPH_SCRIPT="scripts/VisCache/MinimalPathTracer_VisCache_Graph.py" \
SCENE_FILE="data/ReSTIRPTPass/VeachAjar/VeachAjar.pyscene" \
NUM_FRAMES=1 \
    ./Mogwai.exe --headless --script "scripts/VisCache/run_graph_headless.py" 2>&1 \
    | grep -qE '\[headless\] OK' && echo "PASS" || { echo "FAIL"; exit 1; }
