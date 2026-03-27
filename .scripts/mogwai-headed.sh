#!/usr/bin/env bash
# mogwai-headed.sh — Run Mogwai with GPU window. Supports source and synced modes.
#
# Mode resolution (first match wins):
#   1. --source / --synced flag
#   2. VISCACHE_MODE env var ("source" or "synced")
#   3. .scripts/.mode marker file ("source" or "synced")
#   4. Auto: source mode if scripts/ dir exists, else synced
#
# Usage: .scripts/mogwai-headed.sh [--source|--synced] <Graph-pattern> [scene]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNTIME="$PROJECT_ROOT/runtime"
SCRIPTS_SRC="$PROJECT_ROOT/scripts"
MODE_FILE="$SCRIPT_DIR/.mode"

# Parse optional mode flag
FORCE_MODE=""
if [ "${1:-}" = "--source" ] || [ "${1:-}" = "--synced" ]; then
    FORCE_MODE="${1#--}"
    shift
fi

PATTERN="${1:?Usage: mogwai-headed.sh [--source|--synced] <Graph-pattern> [scene]}"
SCENE="${2:-CornellBox_1AreaLight.pyscene}"

cd "$RUNTIME"

# Resolve mode
if [ -n "$FORCE_MODE" ]; then
    MODE="$FORCE_MODE"
elif [ -n "${VISCACHE_MODE:-}" ]; then
    MODE="$VISCACHE_MODE"
elif [ -f "$MODE_FILE" ]; then
    MODE="$(cat "$MODE_FILE" | tr -d '[:space:]')"
elif [ -d "$SCRIPTS_SRC" ]; then
    MODE="source"
else
    MODE="synced"
fi

# Configure paths
if [ "$MODE" = "source" ]; then
    EXPORT_ROOT="$PROJECT_ROOT"
    shopt -s nullglob
    MATCHES=("$SCRIPTS_SRC/"$PATTERN)
    shopt -u nullglob
else
    EXPORT_ROOT=""
    shopt -s nullglob
    MATCHES=("$RUNTIME/scripts/VisCache/"$PATTERN)
    shopt -u nullglob
fi

if [ ${#MATCHES[@]} -eq 0 ]; then
    echo "No scripts matched pattern: $PATTERN (mode: $MODE)"
    exit 1
fi

for MATCH in "${MATCHES[@]}"; do
    NAME="$(basename "$MATCH")"
    echo "=== Running: $NAME [mode: $MODE] ==="
    PROJECT_ROOT="$EXPORT_ROOT" \
        "$RUNTIME/Mogwai.exe" \
        --script "$MATCH" \
        --scene "$SCENE"
done
