#!/usr/bin/env bash
# mogwai-ladder.sh — Run a batch of ladder steps in one Mogwai session.
#
# Eliminates per-step DX12/CUDA startup by running all steps inside a single
# Mogwai process via RunLadderBatch.py.
#
# Usage:
#   .scripts/mogwai-ladder.sh [--source|--synced] [step1.py,step2.py,...]
#
#   Default (no steps arg): all VisCache_Ladder??.py in scripts/
#
# Examples:
#   .scripts/mogwai-ladder.sh                                  # all steps
#   .scripts/mogwai-ladder.sh 'VisCache_Ladder01.py'           # single step
#   .scripts/mogwai-ladder.sh 'VisCache_Ladder01.py,VisCache_Ladder02.py'
#   .scripts/mogwai-ladder.sh --synced                         # all, synced mode
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Pull optional --source/--synced flag
MODE_ARG=""
if [ "${1:-}" = "--source" ] || [ "${1:-}" = "--synced" ]; then
    MODE_ARG="$1"; shift
fi

# Positional arg takes precedence over env var; empty = all ladder scripts
STEPS_ARG="${1:-${LADDER_STEPS:-}}"

export LADDER_STEPS="$STEPS_ARG"

exec "$SCRIPT_DIR/mogwai-headless.sh" ${MODE_ARG:+"$MODE_ARG"} 'RunLadderBatch.py'
