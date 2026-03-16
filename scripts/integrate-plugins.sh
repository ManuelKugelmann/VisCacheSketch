#!/usr/bin/env bash
# integrate-plugins.sh — Copy VisCache/ReSTIRPTPass into Falcor tree and patch CMake.
#
# Usage (from repo root):
#     bash scripts/integrate-plugins.sh [FALCOR_DIR]
#
# Called by build.yml (Linux GCC job) and usable locally.

set -euo pipefail

FALCOR="${1:-Falcor}"

# ------------------------------------------------------------------
# 1. Copy plugin sources into Falcor render-passes directory
# ------------------------------------------------------------------
for pass in VisCache ReSTIRPTPass; do
    dest="${FALCOR}/Source/RenderPasses/${pass}"
    mkdir -p "$dest"
    cp -r "Source/RenderPasses/${pass}/"* "$dest/"
    echo "[integrate] Copied ${pass} -> ${dest}"
done

# Copy data files (16RooksPattern256.txt, VeachAjar pyscenes) into Falcor/data/
# so AssetResolver finds them at runtime without waiting for CMake POST_BUILD.
if [ -d "Source/RenderPasses/ReSTIRPTPass/Data" ]; then
    mkdir -p "${FALCOR}/data/ReSTIRPTPass"
    cp -r Source/RenderPasses/ReSTIRPTPass/Data/* "${FALCOR}/data/ReSTIRPTPass/"
    echo "[integrate] Copied ReSTIRPTPass data -> ${FALCOR}/data/ReSTIRPTPass/"
fi

mkdir -p "${FALCOR}/scripts/VisCache"
cp -r scripts/* "${FALCOR}/scripts/VisCache/"
echo "[integrate] Copied scripts -> ${FALCOR}/scripts/VisCache/"

# Copy tests
if [ -d "tests" ]; then
    mkdir -p "${FALCOR}/scripts/VisCache/tests"
    cp -r tests/* "${FALCOR}/scripts/VisCache/tests/"
    echo "[integrate] Copied tests -> ${FALCOR}/scripts/VisCache/tests/"
fi

# ------------------------------------------------------------------
# 2. Patch RenderPasses/CMakeLists.txt to add our subdirectories
# ------------------------------------------------------------------
RP_CMAKE="${FALCOR}/Source/RenderPasses/CMakeLists.txt"
for sub in VisCache ReSTIRPTPass; do
    if ! grep -q "add_subdirectory(${sub})" "$RP_CMAKE"; then
        echo "add_subdirectory(${sub})" >> "$RP_CMAKE"
        echo "[integrate] Patched ${RP_CMAKE}: added ${sub}"
    fi
done

echo "[integrate] Done."
cat "$RP_CMAKE"
