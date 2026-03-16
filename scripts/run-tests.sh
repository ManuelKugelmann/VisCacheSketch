#!/usr/bin/env bash
# VisCacheSketch — run all CPU algorithm tests (no GPU needed).
#
# Usage:
#     ./scripts/run-tests.sh            Run all 3 test suites
#     ./scripts/run-tests.sh quick      Run convergence tests only
#
# Windows alternative: scripts\run-tests.bat

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

PASS=0
FAIL=0

run_suite() {
    local name="$1"
    local script="$2"
    echo "=== $name ==="
    if python3 "$ROOT_DIR/$script"; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
    fi
    echo
}

if [ "${1:-}" = "quick" ]; then
    run_suite "VisCache convergence (14 tests)" "tests/test_viscache_convergence.py"
else
    run_suite "VisCache convergence (14 tests)" "tests/test_viscache_convergence.py"
    run_suite "ReSTIR variants (8 tests)" "tests/test_restir_variants.py"
    run_suite "Paper ablations (17 tests)" "tests/test_paper_ablations.py"
fi

echo "========================================"
echo "  $PASS suite(s) passed, $FAIL suite(s) failed"
echo "========================================"
[ "$FAIL" -eq 0 ]
