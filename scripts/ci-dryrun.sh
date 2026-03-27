#!/usr/bin/env bash
# ci-dryrun.sh — Local dry-run of CI checks (no GPU needed).
#
# Catches script syntax errors, missing enum symbols, Python import
# failures, and algorithm-test regressions *before* pushing.
#
# Usage:
#     bash scripts/ci-dryrun.sh           Run all checks
#     bash scripts/ci-dryrun.sh quick     Skip algorithm tests

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

PASS=0
FAIL=0
TOTAL=0

echo "========================================"
echo " VisCacheSketch CI dry-run"
echo "========================================"
echo

# -------------------------------------------------------------------
# 1. Python syntax check on all render-graph / smoke-test scripts
# -------------------------------------------------------------------
echo "[1/4] Checking Python syntax (render graph scripts)..."
TOTAL=$((TOTAL + 1))
SYNTAX_FAIL=0
for f in "$ROOT_DIR"/scripts/*.py; do
    [ -f "$f" ] || continue
    if python3 -m py_compile "$f" 2>/dev/null; then
        echo "  OK:   $(basename "$f")"
    else
        echo "  FAIL: $(basename "$f")"
        SYNTAX_FAIL=1
    fi
done
if [ "$SYNTAX_FAIL" -eq 0 ]; then
    echo "  All scripts parse OK."
    PASS=$((PASS + 1))
else
    echo "  FAIL: syntax errors found."
    FAIL=$((FAIL + 1))
fi
echo

# -------------------------------------------------------------------
# 2. Check for stale Falcor 4.x enum usage in graph scripts
#    (SamplePattern.xxx, CullMode.CullXxx, RTXDIOptions(...), etc.)
# -------------------------------------------------------------------
echo "[2/4] Checking for stale Falcor 4.x enum references..."
TOTAL=$((TOTAL + 1))
ENUM_FAIL=0
STALE_PATTERN='SamplePattern\.\|CullMode\.\|RTXDIMode\.\|RTXDIOptions(\|ColorFormat\.\|NRDMethod\.\|ToneMapOp\.'
for f in "$ROOT_DIR"/scripts/VisCache_*.py "$ROOT_DIR"/scripts/SmokeTest.py; do
    [ -f "$f" ] || continue
    if grep -n "$STALE_PATTERN" "$f" >/dev/null 2>&1; then
        echo "  FAIL: $(basename "$f") contains old-style enum references:"
        grep -n "$STALE_PATTERN" "$f" | sed 's/^/    /'
        ENUM_FAIL=1
    fi
done
if [ "$ENUM_FAIL" -eq 0 ]; then
    echo "  No stale enums found."
    PASS=$((PASS + 1))
else
    echo "  FAIL: use string literals instead of enum objects in Falcor 8."
    FAIL=$((FAIL + 1))
fi
echo

# -------------------------------------------------------------------
# 3. Check data file deployment (16RooksPattern256.txt)
# -------------------------------------------------------------------
echo "[3/4] Checking data file presence..."
TOTAL=$((TOTAL + 1))
DATA_SRC="$ROOT_DIR/Source/RenderPasses/ReSTIRPTPass/Data/16RooksPattern256.txt"
if [ -f "$DATA_SRC" ]; then
    echo "  OK: source data file exists"
    PASS=$((PASS + 1))
else
    echo "  FAIL: $DATA_SRC not found"
    FAIL=$((FAIL + 1))
fi
echo

# -------------------------------------------------------------------
# 4. Algorithm validation tests (CPU-only, skip with "quick")
# -------------------------------------------------------------------
if [ "${1:-}" = "quick" ]; then
    echo "[4/4] Algorithm tests skipped (quick mode)."
    echo
else
    echo "[4/4] Running algorithm validation tests..."
    TOTAL=$((TOTAL + 1))
    if bash "$ROOT_DIR/scripts/run-tests.sh"; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
    fi
    echo
fi

# -------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------
echo "========================================"
echo " CI dry-run: $PASS/$TOTAL passed, $FAIL failed"
echo "========================================"

if [ "$FAIL" -gt 0 ]; then
    echo " Some checks failed. Fix before pushing."
    exit 1
fi
echo " All checks passed."
exit 0
