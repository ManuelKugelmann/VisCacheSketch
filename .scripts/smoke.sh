#!/usr/bin/env bash
# smoke.sh — Quick build validation: load one graph, render 1 frame with scene.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

OUTPUT=$("$SCRIPT_DIR/mogwai-headless.sh" 'MinimalPathTracer_VisCache_Graph.py' 'CornellBox_1AreaLight.pyscene' 1 2>&1)
echo "$OUTPUT"
if echo "$OUTPUT" | grep -qF '[headless] OK'; then
    echo "PASS"
else
    echo "FAIL"
    exit 1
fi
