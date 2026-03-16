#!/usr/bin/env bash
# verify-build-output.sh — Check that build output directory has required files.
#
# Usage:
#     bash scripts/verify-build-output.sh OUTDIR
#
# Checks: 16RooksPattern256.txt data file.
# Called by build.yml (Linux job) and usable locally.

set -euo pipefail

OUTDIR="${1:?Usage: verify-build-output.sh OUTDIR}"

echo "[verify] Checking build output in ${OUTDIR}..."

FAIL=0

if [ ! -f "$OUTDIR/data/ReSTIRPTPass/16RooksPattern256.txt" ]; then
    echo "[verify] FAIL: 16RooksPattern256.txt missing from build output"
    ls -R "$OUTDIR/data" 2>/dev/null || echo "[verify] No data directory found"
    FAIL=1
else
    echo "[verify] OK: data files deployed"
fi

if [ "$FAIL" -ne 0 ]; then
    exit 1
fi

echo "[verify] All checks passed."
