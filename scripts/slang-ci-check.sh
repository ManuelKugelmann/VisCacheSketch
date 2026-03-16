#!/usr/bin/env bash
# slang-ci-check.sh — Offline Slang shader compilation for CI.
#
# Mirrors Falcor's ProgramManager::createSlangCompileRequest() as closely as
# possible, without a GPU:
#
#   - Front-end only (-no-codegen) — same as Falcor's initial compile pass
#     (SLANG_COMPILE_FLAG_NO_CODEGEN).  Type conformances are applied at
#     specialization time, so codegen errors like 50100 don't apply here.
#   - Row-major matrices (-matrix-layout-row-major)
#   - Short-circuit disabled (-disable-short-circuit)
#   - Warning suppressions matching ProgramManager (15602, 30056, 30081, 41203)
#   - Include paths: Source/Falcor, Source, external/packman/nanovdb/include
#   - Platform defines: FALCOR_VULKAN=1, __SM_6_6__=1
#
# Usage: scripts/slang-ci-check.sh <path-to-slangc>

set -euo pipefail

SLANGC="${1:?Usage: $0 <path-to-slangc>}"
RESULTS="slang-check-results.log"
: > "$RESULTS"

PASS=0
FAIL=0

if [ -t 1 ]; then
  GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
else
  GREEN=''; RED=''; NC=''
fi

check() {
  local file="$1"; shift

  printf "  %-65s " "$file"

  # shellcheck disable=SC2068
  if output=$("$SLANGC" $@ "$file" 2>&1); then
    printf "${GREEN}OK${NC}\n"
    echo "OK   $file" >> "$RESULTS"
    PASS=$((PASS + 1))
  else
    printf "${RED}FAIL${NC}\n"
    echo "FAIL $file" >> "$RESULTS"
    echo "$output" >> "$RESULTS"
    echo "$output" >&2
    FAIL=$((FAIL + 1))
  fi
}

echo "=== Slang Shader CI Check ==="
echo ""

# ---------------------------------------------------------------------------
# Setup: copy render passes into Falcor tree (same as build.yml / CMake)
# ---------------------------------------------------------------------------
FALCOR="Falcor"
echo "Integrating render passes into Falcor source tree..."
mkdir -p "${FALCOR}/Source/RenderPasses/VisCache"
cp -r Source/RenderPasses/VisCache/* "${FALCOR}/Source/RenderPasses/VisCache/"
mkdir -p "${FALCOR}/Source/RenderPasses/ReSTIRPTPass"
cp -r Source/RenderPasses/ReSTIRPTPass/* "${FALCOR}/Source/RenderPasses/ReSTIRPTPass/"
echo ""

# ---------------------------------------------------------------------------
# Download PNanoVDB.h if not present (needed by Falcor's Grid.slang)
# ---------------------------------------------------------------------------
NANOVDB_DIR="${FALCOR}/external/packman/nanovdb/include/nanovdb"
if [ ! -f "${NANOVDB_DIR}/PNanoVDB.h" ]; then
  echo "Downloading PNanoVDB.h ..."
  mkdir -p "${NANOVDB_DIR}"
  curl -fsSL "https://raw.githubusercontent.com/AcademySoftwareFoundation/openvdb/v11.0.0/nanovdb/nanovdb/PNanoVDB.h" \
    -o "${NANOVDB_DIR}/PNanoVDB.h"
fi

# ---------------------------------------------------------------------------
# Generate -D flags from slang-ci-defines.slangh
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DFLAGS=$(grep '^#define ' "${SCRIPT_DIR}/slang-ci-defines.slangh" \
  | sed 's|//.*||; s/[[:space:]]*$//' \
  | sed 's/^#define \([A-Za-z_][A-Za-z_0-9]*\) \(.*\)/-D\1=\2/' \
  | sed 's/^#define \([A-Za-z_][A-Za-z_0-9]*\)$/-D\1/' \
  | tr '\n' ' ')

# ---------------------------------------------------------------------------
# Flags — mirrors Falcor ProgramManager::createSlangCompileRequest()
# ---------------------------------------------------------------------------
# Include paths (getShaderDirectoriesList in dev mode)
SEARCH_PATHS="-I ${FALCOR}/Source/Falcor -I ${FALCOR}/Source -I ${FALCOR}/external/packman/nanovdb/include"

# Platform & shader model defines (added by ProgramManager)
PLATFORM_DEFS="-DFALCOR_VULKAN=1 -D__SM_6_6__=1"

# Compiler flags matching ProgramManager (lines 732-767 of ProgramManager.cpp)
COMPILER_FLAGS="-matrix-layout-row-major -disable-short-circuit -capability sm_6_6+spirv_1_5+raytracingstages_compute_fragment_geometry_vertex"

# Warning suppressions matching ProgramManager
WARN_FLAGS="-Wno-15602 -Wno-30056 -Wno-30081 -Wno-41203"

# Front-end only — matches Falcor's SLANG_COMPILE_FLAG_NO_CODEGEN.
# Type conformances (IMaterial, IMaterialInstance) are provided at runtime
# by MaterialSystem::getTypeConformances(); front-end check doesn't need them.
CODEGEN="-no-codegen"

# VisCache consumer stubs (traceShadowRay / evalBRDF / ShadingData — normally
# provided by the host pass that imports VisCache modules)
VC_STUBS="${SCRIPT_DIR}/slang-ci-viscache-stubs.slang"

# Common flags for all Falcor-dependent shaders
COMMON="-target spirv ${CODEGEN} ${COMPILER_FLAGS} ${WARN_FLAGS} ${SEARCH_PATHS} ${PLATFORM_DEFS} ${DFLAGS}"

VISCACHE_DIR="${FALCOR}/Source/RenderPasses/VisCache"
PT_DIR="${FALCOR}/Source/RenderPasses/PathTracer"
RTXDI_DIR="${FALCOR}/Source/RenderPasses/RTXDIPass"
RESTIR_DIR="${FALCOR}/Source/RenderPasses/ReSTIRPTPass"

# ===========================================================================
# VisCache — self-contained core + Falcor-dependent modules
# ===========================================================================
echo "--- VisCache ---"

# Self-contained (no Falcor imports)
check "${VISCACHE_DIR}/VisCache.slang" \
  -target spirv ${CODEGEN}

check "${VISCACHE_DIR}/VisCacheInsert.cs.slang" \
  -target spirv ${CODEGEN} -I "${VISCACHE_DIR}" -entry csInsert -stage compute

check "${VISCACHE_DIR}/VisCacheDecay.cs.slang" \
  -target spirv ${CODEGEN} -I "${VISCACHE_DIR}" -entry csDecay -stage compute

# Falcor-dependent (VC_STUBS provide consumer functions: traceShadowRay, evalBRDF)
check "${VISCACHE_DIR}/VisCacheTracing.slang" \
  ${COMMON} "${VC_STUBS}"

check "${VISCACHE_DIR}/ShadingCV.slang" \
  ${COMMON} "${VC_STUBS}"

check "${VISCACHE_DIR}/RevalidationCommon.slang" \
  ${COMMON} "${VC_STUBS}"

echo ""

# ===========================================================================
# PathTracer — entry-point shaders
# ===========================================================================
echo "--- PathTracer ---"

PT_FLAGS="${COMMON} -I ${PT_DIR}"

check "${PT_DIR}/GeneratePaths.cs.slang" \
  ${PT_FLAGS} -entry main -stage compute

check "${PT_DIR}/ReflectTypes.cs.slang" \
  ${PT_FLAGS} -entry main -stage compute

check "${PT_DIR}/ResolvePass.cs.slang" \
  ${PT_FLAGS} -entry main -stage compute

check "${PT_DIR}/TracePass.rt.slang" \
  ${PT_FLAGS}

echo ""

# ===========================================================================
# RTXDIPass — entry-point shaders
# ===========================================================================
echo "--- RTXDIPass ---"

RTXDI_FLAGS="${COMMON} -I ${RTXDI_DIR}"

check "${RTXDI_DIR}/PrepareSurfaceData.cs.slang" \
  ${RTXDI_FLAGS} -entry main -stage compute

# FinalShading.cs.slang accesses gRTXDI.frameIndex which requires the RTXDI
# SDK (RTXDI_INSTALLED=1).  At runtime Falcor only compiles this shader when
# the SDK is present, so we skip it in CI — same as Falcor would.
echo "  (skip FinalShading.cs.slang — requires RTXDI SDK)"

echo ""

# ===========================================================================
# ReSTIRPTPass — entry-point shaders
# ===========================================================================
echo "--- ReSTIRPTPass ---"

RESTIR_FLAGS="${COMMON} -I ${RESTIR_DIR}"

if [ -d "$RESTIR_DIR" ]; then
  for f in "$RESTIR_DIR"/*.cs.slang; do
    [ -f "$f" ] || continue
    entry=$(grep -oP '(?<=void )\w+(?=\()' "$f" | tail -1 || true)
    [ -n "$entry" ] || continue
    check "$f" \
      ${RESTIR_FLAGS} -entry "$entry" -stage compute
  done
fi

echo ""

# ===========================================================================
# Summary
# ===========================================================================
TOTAL=$((PASS + FAIL))
echo "=== Results: ${PASS} passed, ${FAIL} failed (${TOTAL} total) ==="
echo "" >> "$RESULTS"
echo "Total: ${PASS} passed, ${FAIL} failed" >> "$RESULTS"

if [ "$FAIL" -gt 0 ]; then
  echo ""
  printf "${RED}Shader compilation failed — see errors above.${NC}\n"
  exit 1
fi

echo ""
echo "All shaders compiled successfully."
