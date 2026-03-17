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

# ---- NRD denoiser DLLs (warn loudly, do not fail) ----
NRD_WARN=0
if [ ! -f "$OUTDIR/NRDPass.dll" ]; then
    NRD_WARN=1
    echo ""
    echo "========================================================"
    echo " WARNING: NRDPass.dll MISSING from build output"
    echo "========================================================"
    echo ""
fi
if [ ! -f "$OUTDIR/NRD.dll" ]; then
    NRD_WARN=1
    echo ""
    echo "========================================================"
    echo " WARNING: NRD.dll MISSING from build output"
    echo "========================================================"
    echo ""
fi
if [ "$NRD_WARN" -ne 0 ]; then
    echo "[verify] WARNING: NRD denoiser not in build output -- output will be raw noisy radiance."
    echo "[verify] Rebuild with D3D12 + packman NRD package, or ensure NRDPass is enabled in CMake."
    echo ""
else
    echo "[verify] OK: NRDPass.dll and NRD.dll present"
fi

if [ "$FAIL" -ne 0 ]; then
    exit 1
fi

echo "[verify] All checks passed."
