#!/usr/bin/env bash
# mogwai-headed.sh — Run Mogwai with GPU window from anywhere (handles cd to runtime/).
#
# Usage: .scripts/mogwai-headed.sh <Graph-pattern> [scene.pyscene]
#   Graph: graph script name or glob pattern (matched in scripts/VisCache/)
#          If pattern matches multiple scripts, runs each sequentially.
#   Scene: scene path relative to runtime/ (default: CornellBox)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNTIME="$PROJECT_ROOT/runtime"

PATTERN="${1:?Usage: mogwai-headed.sh <Graph-pattern> [scene]}"
SCENE="${2:-media/scenes/CornellBox.pyscene}"

cd "$RUNTIME"

# Expand glob pattern against scripts/VisCache/
shopt -s nullglob
MATCHES=("$RUNTIME/scripts/VisCache/"$PATTERN)
shopt -u nullglob

if [ ${#MATCHES[@]} -eq 0 ]; then
    echo "No scripts matched pattern: $PATTERN"
    exit 1
fi

for MATCH in "${MATCHES[@]}"; do
    SCRIPT="${MATCH#$RUNTIME/}"
    NAME="$(basename "$SCRIPT")"
    echo "=== Running: $NAME ==="
    "$RUNTIME/Mogwai.exe" \
        --script "$SCRIPT" \
        --scene "$SCENE"
done
