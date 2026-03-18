#!/usr/bin/env bash
# mogwai-headed.sh — Run Mogwai with GPU window from anywhere (handles cd to release/).
#
# Usage: .scripts/mogwai-headed.sh <Graph-pattern> [scene.pyscene]
#   Graph: graph script name or glob pattern (matched in scripts/VisCache/)
#          If pattern matches multiple scripts, runs each sequentially.
#   Scene: scene path relative to release/ (default: VeachAjar)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RELEASE="$ROOT/release"

PATTERN="${1:?Usage: mogwai-headed.sh <Graph-pattern> [scene]}"
SCENE="${2:-data/ReSTIRPTPass/VeachAjar/VeachAjar.pyscene}"

cd "$RELEASE"

# Expand glob pattern against scripts/VisCache/
shopt -s nullglob
MATCHES=(scripts/VisCache/$PATTERN)
shopt -u nullglob

if [ ${#MATCHES[@]} -eq 0 ]; then
    echo "No scripts matched pattern: $PATTERN"
    exit 1
fi

for SCRIPT in "${MATCHES[@]}"; do
    NAME="$(basename "$SCRIPT")"
    echo "=== Running: $NAME ==="
    ./Mogwai.exe \
        --script "$SCRIPT" \
        --scene "$SCENE"
done
