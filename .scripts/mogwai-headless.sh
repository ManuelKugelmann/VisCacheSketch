#!/usr/bin/env bash
# mogwai-headless.sh — Run Mogwai headless. Supports source and synced modes.
#
# Mode resolution (first match wins):
#   1. --source / --synced flag
#   2. VISCACHE_MODE env var ("source" or "synced")
#   3. .scripts/.mode marker file ("source" or "synced")
#   4. Auto: source mode if scripts/ dir exists, else synced
#
# Source mode: scripts and scenes served from project source tree (no sync needed).
# Synced mode: uses runtime/ copies (CI, or when editing scripts while running experiments).
#
# Usage: .scripts/mogwai-headless.sh [--source|--synced] <Graph-pattern> [scene] [frames]
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

PATTERN="${1:?Usage: mogwai-headless.sh [--source|--synced] <Graph-pattern> [scene] [frames]}"
SCENE="${2:-}"  # empty = let script's get_scenes() use ALL_SCENES
FRAMES="${3:-2}"

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

# Configure paths for selected mode
if [ "$MODE" = "source" ]; then
    HARNESS="$SCRIPTS_SRC/RunGraphHeadless.py"
    EXPORT_ROOT="$PROJECT_ROOT"
    shopt -s nullglob
    MATCHES=("$SCRIPTS_SRC/"$PATTERN)
    shopt -u nullglob
else
    HARNESS="$RUNTIME/scripts/VisCache/RunGraphHeadless.py"
    EXPORT_ROOT=""
    shopt -s nullglob
    MATCHES=("$RUNTIME/scripts/VisCache/"$PATTERN)
    shopt -u nullglob
fi

if [ ${#MATCHES[@]} -eq 0 ]; then
    echo "No scripts matched pattern: $PATTERN (mode: $MODE)"
    exit 1
fi

PASS=0
FAIL=0

for MATCH in "${MATCHES[@]}"; do
    NAME="$(basename "$MATCH")"
    echo "=== Testing: $NAME ==="
    # Only override SCENE_FILE when a scene arg was given; otherwise let outer env (or script default) through.
    if [ -n "$SCENE" ]; then
        SCENE_FILE_ARG="SCENE_FILE=$SCENE"
    else
        SCENE_FILE_ARG=""
    fi
    if env PROJECT_ROOT="$EXPORT_ROOT" GRAPH_SCRIPT="$MATCH" NUM_FRAMES="$FRAMES" \
        ${SCENE_FILE_ARG:+"$SCENE_FILE_ARG"} \
        "$RUNTIME/Mogwai.exe" --headless \
        --script "$HARNESS" 2>&1; then
        echo "=== PASS: $NAME ==="
        PASS=$((PASS + 1))
    else
        echo "=== FAIL: $NAME ==="
        FAIL=$((FAIL + 1))
    fi
    echo ""
done

echo "Results: $PASS passed, $FAIL failed (out of ${#MATCHES[@]} scripts) [mode: $MODE]"
[ $FAIL -eq 0 ]
