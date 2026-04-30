#!/usr/bin/env bash
# restirpt_baseline_run.sh — drive ReSTIRPT_Baseline_Test.py one cell at a time
# (one Mogwai per VARIANT × BOUNCE) to stay under Slang's per-process permutation
# budget. Already-captured cells are skipped by the Python script.
#
# Env overrides:
#   SCENES   : comma-separated stems, default = CornellBox_1AreaLight only
#   BOUNCES  : space-separated bounce counts (default "1 4 8")
#   VARIANTS : space-separated variants (default "vanilla restirpt")
#   SPP      : samples/pixel/frame (default 1)
#   WARMUP   : warmup frames (default 8)
#   CAPTURE  : capture frames (default 32)
#
# Usage examples:
#   # CornellBox first, all variants × bounces
#   SCENES=CornellBox_1AreaLight ./.scripts/restirpt_baseline_run.sh
#
#   # Escalate to demanding scenes
#   SCENES=BistroInterior,Sponza,VeachAjar BOUNCES="1 4 8" ./.scripts/restirpt_baseline_run.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

: "${SCENES:=CornellBox_1AreaLight}"
: "${BOUNCES:=1 4 8}"
: "${VARIANTS:=vanilla restirpt}"
: "${SPP:=1}"
: "${WARMUP:=8}"
: "${CAPTURE:=32}"

PASS=0
FAIL=0
TOTAL=0

for V in $VARIANTS; do
    for B in $BOUNCES; do
        TOTAL=$((TOTAL + 1))
        echo ""
        echo "============================================================"
        echo "  CELL: variant=$V  bounce=$B  scenes=$SCENES"
        echo "============================================================"
        if env VARIANT="$V" BOUNCE="$B" SCENES="$SCENES" SPP="$SPP" \
               WARMUP="$WARMUP" CAPTURE="$CAPTURE" \
            "$SCRIPT_DIR/mogwai-headless.sh" ReSTIRPT_Baseline_Test.py; then
            PASS=$((PASS + 1))
            echo "  -> PASS  ($V b$B)"
        else
            FAIL=$((FAIL + 1))
            echo "  -> FAIL  ($V b$B)"
        fi
    done
done

echo ""
echo "============================================================"
echo "  ReSTIRPT_Baseline_Run summary: $PASS / $TOTAL cells passed, $FAIL failed"
echo "  Output: $PROJECT_ROOT/runtime/captures/restirpt_baseline/"
echo "============================================================"
[ $FAIL -eq 0 ]
