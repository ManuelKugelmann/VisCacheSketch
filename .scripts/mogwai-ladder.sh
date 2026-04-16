#!/usr/bin/env bash
# mogwai-ladder.sh — Run ladder steps, one Mogwai process per scene.
#
# Outer scene loop (fresh Mogwai per scene) avoids Slang's internal compiler
# fatigue (~60 permutations per process) on large-variant steps. Inside each
# Mogwai process, RunLadderBatch.py runs all requested steps sequentially —
# saving DX12/CUDA/Python startup between steps while keeping scenes
# isolated. Additive runs: rerun for a single scene without disturbing
# captures for the others (captures/CSV are upsert-keyed).
#
# Steps and scenes accept comma OR whitespace separators. Empty scenes arg =
# the authoritative ALL_SCENES list in VisCache_LadderCommon.py — edit that
# list when adding a scene (shell picks it up automatically).
#
# Usage:
#   .scripts/mogwai-ladder.sh [--source|--synced] <steps> [scenes]
#
# Scene names accept the bare stem (CornellBox_1AreaLight) — ".pyscene" is
# appended automatically. Step names accept bare "06" or the full script name.
#
# Examples:
#   .scripts/mogwai-ladder.sh 06                                            # step 06, ALL_SCENES
#   .scripts/mogwai-ladder.sh "05 06 07 08"                                 # four single-level steps
#   .scripts/mogwai-ladder.sh 06 CornellBox_1AreaLight                       # one scene
#   .scripts/mogwai-ladder.sh 06,12 CornellBox_1AreaLight,CornellBox_3AreaLights
#   .scripts/mogwai-ladder.sh "" Arcade                                      # all steps, one scene
#
# For a single-process run of everything (fast but Slang-risky on big
# sweeps), set LADDER_STEPS + LADDER_SCENES and invoke RunLadderBatch.py
# via mogwai-headless.sh directly.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

MODE_ARG=""
if [ "${1:-}" = "--source" ] || [ "${1:-}" = "--synced" ]; then
    MODE_ARG="$1"; shift
fi

STEPS_ARG="${1-}"
SCENES_ARG="${2-}"

# Default scenes come from the authoritative ALL_SCENES list in LadderCommon —
# single source of truth when the scene set grows. Convert MSYS path to
# Windows form so the Windows Python interpreter can resolve sys.path entries.
if [ -z "$SCENES_ARG" ]; then
    SCRIPTS_WIN="$(cygpath -w "$PROJECT_ROOT/scripts" 2>/dev/null || echo "$PROJECT_ROOT/scripts")"
    SCENES_ARG="$("$PROJECT_ROOT/runtime/pythondist/python.exe" -c "
import sys
sys.path.insert(0, r'$SCRIPTS_WIN')
from VisCache_LadderCommon import ALL_SCENES
print(','.join(ALL_SCENES))
")"
fi

# Normalize separators: accept comma or whitespace.
STEPS=$(echo "${STEPS_ARG// /,}"  | tr ',' '\n' | sed '/^$/d')
SCENES=$(echo "${SCENES_ARG// /,}" | tr ',' '\n' | sed '/^$/d')

# Build LADDER_STEPS for RunLadderBatch. Empty → RunLadderBatch default (all).
if [ -n "$STEPS_ARG" ]; then
    # Prefix each with VisCache_Ladder and suffix with .py for convenience:
    # accept bare "06" or full "VisCache_Ladder06.py".
    LADDER_STEPS_VAL=""
    while IFS= read -r s; do
        case "$s" in
            VisCache_Ladder*.py) name="$s" ;;
            *)                   name="VisCache_Ladder${s}.py" ;;
        esac
        LADDER_STEPS_VAL="${LADDER_STEPS_VAL:+$LADDER_STEPS_VAL,}$name"
    done <<< "$STEPS"
else
    LADDER_STEPS_VAL=""
fi

TOTAL_PASS=0
TOTAL_FAIL=0
FAILURES=()

while IFS= read -r SCENE; do
    [ -z "$SCENE" ] && continue
    # Accept bare "CornellBox_1AreaLight" as well as the full ".pyscene" name.
    case "$SCENE" in
        *.pyscene) ;;
        *)         SCENE="${SCENE}.pyscene" ;;
    esac
    echo ""
    echo "### [$(date +%H:%M:%S)] scene=$SCENE steps=${LADDER_STEPS_VAL:-<all>} ###"
    if LADDER_STEPS="$LADDER_STEPS_VAL" LADDER_SCENES="$SCENE" \
        "$SCRIPT_DIR/mogwai-headless.sh" ${MODE_ARG:+"$MODE_ARG"} 'RunLadderBatch.py'; then
        TOTAL_PASS=$((TOTAL_PASS + 1))
    else
        TOTAL_FAIL=$((TOTAL_FAIL + 1))
        FAILURES+=("scene=$SCENE")
    fi
done <<< "$SCENES"

echo ""
echo "=== mogwai-ladder.sh summary: $TOTAL_PASS passed, $TOTAL_FAIL failed ==="
if [ ${TOTAL_FAIL} -ne 0 ]; then
    printf '  FAIL: %s\n' "${FAILURES[@]}"
    exit 1
fi
