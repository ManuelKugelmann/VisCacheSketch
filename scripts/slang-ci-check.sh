#!/usr/bin/env bash
# slang-ci-check.sh — Offline Slang shader compilation for CI.
#
# Mirrors Falcor's ProgramManager::createSlangCompileRequest() as closely as
# possible, without a GPU:
#
#   - Front-end only (-no-codegen) — same as Falcor's initial compile pass
#     (SLANG_COMPILE_FLAG_NO_CODEGEN).  Type conformances are applied at
#     specialization time, so codegen errors like 50100 don't apply here.
#   - DXIL target with sm_6_6 profile (matches Falcor's D3D12 backend)
#   - Row-major matrices (-matrix-layout-row-major)
#   - Short-circuit disabled (-disable-short-circuit)
#   - Warning suppressions matching ProgramManager (15602, 30056, 30081, 41203)
#   - Include paths: Source/Falcor, Source, external/packman/nanovdb/include
#   - Platform defines: FALCOR_D3D12=1, __SM_6_6__=1
#
# Compiles ALL Falcor render-pass entry-point shaders (.cs.slang / .rt.slang).
#
# Usage: scripts/slang-ci-check.sh <path-to-slangc>

set -euo pipefail

SLANGC="${1:?Usage: $0 <path-to-slangc>}"
RESULTS="slang-check-results.log"
: > "$RESULTS"

PASS=0
FAIL=0
SKIP=0

if [ -t 1 ]; then
  GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[0;33m'; NC='\033[0m'
else
  GREEN=''; RED=''; YELLOW=''; NC=''
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

skip() {
  local file="$1"; shift
  local reason="$1"
  printf "  %-65s ${YELLOW}SKIP${NC} (%s)\n" "$file" "$reason"
  echo "SKIP $file ($reason)" >> "$RESULTS"
  SKIP=$((SKIP + 1))
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
# Falcor targets D3D12 (DXIL) with sm_6_6 — match exactly for [require(sm_6_6)]
PLATFORM_DEFS="-DFALCOR_D3D12=1 -D__SM_6_6__=1"

# Compiler flags matching ProgramManager (lines 732-767 of ProgramManager.cpp)
# Profile sm_6_6 matching Falcor's ProgramManager.  -ignore-capabilities so
# [require(sm_6_6)] doesn't error on GL_NV_compute_shader_derivatives (ddx/ddy
# in compute shaders via NVAPI, which isn't available in CI).
COMPILER_FLAGS="-matrix-layout-row-major -disable-short-circuit -profile sm_6_6 -ignore-capabilities"

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
# Target DXIL (matching Falcor's D3D12 backend) — [require(sm_6_6)] needs this.
COMMON="-target dxil ${CODEGEN} ${COMPILER_FLAGS} ${WARN_FLAGS} ${SEARCH_PATHS} ${PLATFORM_DEFS} ${DFLAGS}"

RP_DIR="${FALCOR}/Source/RenderPasses"
VISCACHE_DIR="${RP_DIR}/VisCache"

# ---------------------------------------------------------------------------
# Skip list: shaders that need external SDKs not available in CI
# ---------------------------------------------------------------------------
# FinalShading.cs.slang — accesses gRTXDI.frameIndex (needs RTXDI SDK)
# TestPyTorchPass.cs.slang — needs PyTorch/CUDA interop
declare -A SKIP_FILES
SKIP_FILES["FinalShading.cs.slang"]="requires RTXDI SDK"
SKIP_FILES["TestPyTorchPass.cs.slang"]="requires PyTorch interop"
SKIP_FILES["PackRadiance.cs.slang"]="requires NRD SDK"
SKIP_FILES["BSDFOptimizer.cs.slang"]="differentiable programming (error 41020)"

# ===========================================================================
# VisCache — self-contained core + Falcor-dependent modules
# ===========================================================================
echo "--- VisCache ---"

# Self-contained (no Falcor imports).
# VisCache.slang wraps everything in #if USE_VISCACHE — test both paths:
#   USE_VISCACHE=0: compiles to nothing (guards work correctly)
#   USE_VISCACHE=1: full module (types, resources, functions)
check "${VISCACHE_DIR}/VisCache.slang" \
  -target dxil ${CODEGEN}

check "${VISCACHE_DIR}/VisCache.slang" \
  -target dxil ${CODEGEN} -DUSE_VISCACHE=1

# Internal compute shaders: always part of the VisCache pass, need USE_VISCACHE=1
check "${VISCACHE_DIR}/VisCacheInsert.cs.slang" \
  -target dxil ${CODEGEN} -I "${VISCACHE_DIR}" -DUSE_VISCACHE=1 -entry csInsert -stage compute

check "${VISCACHE_DIR}/VisCacheDecay.cs.slang" \
  -target dxil ${CODEGEN} -I "${VISCACHE_DIR}" -DUSE_VISCACHE=1 -entry csDecay -stage compute

# Falcor-dependent (VC_STUBS provide consumer functions: traceShadowRay, evalBRDF).
# USE_VISCACHE=1 needed for RevalidationCommon (uses gPMin, gFireflyBudget from cbuffer).
# Strip -DUSE_VISCACHE=0 from DFLAGS to avoid conflict with the override.
VC_DFLAGS=$(echo "$DFLAGS" | sed 's/-DUSE_VISCACHE=[0-9]*//')
VC_COMMON="-target dxil ${CODEGEN} ${COMPILER_FLAGS} ${WARN_FLAGS} ${SEARCH_PATHS} ${PLATFORM_DEFS} ${VC_DFLAGS} -DUSE_VISCACHE=1"

check "${VISCACHE_DIR}/VisCacheTracing.slang" \
  ${VC_COMMON} "${VC_STUBS}"

check "${VISCACHE_DIR}/ShadingCV.slang" \
  ${VC_COMMON} "${VC_STUBS}"

check "${VISCACHE_DIR}/RevalidationCommon.slang" \
  ${VC_COMMON} "${VC_STUBS}"

echo ""

# ===========================================================================
# All Falcor render passes — auto-discover .cs.slang and .rt.slang
# ===========================================================================
# Iterate every render-pass directory and compile all entry-point shaders,
# exactly as Falcor's ProgramManager would at runtime.

for pass_dir in "${RP_DIR}"/*/; do
  pass_name=$(basename "$pass_dir")

  # VisCache entry points are handled above (self-contained + stubs)
  [ "$pass_name" = "VisCache" ] && continue

  # Collect entry-point files (.cs.slang and .rt.slang)
  shaders=$(find "$pass_dir" -name '*.cs.slang' -o -name '*.rt.slang' | sort)

  [ -z "$shaders" ] && continue

  echo "--- ${pass_name} ---"

  PASS_FLAGS="${COMMON} -I ${pass_dir}"

  while IFS= read -r f; do
    fname=$(basename "$f")

    # Check skip list
    if [ -n "${SKIP_FILES[$fname]+x}" ]; then
      skip "$f" "${SKIP_FILES[$fname]}"
      continue
    fi

    if [[ "$fname" == *.rt.slang ]]; then
      # Raytracing shaders — no explicit entry point / stage
      check "$f" ${PASS_FLAGS}
    else
      # Compute shaders — detect entry point name from source
      entry=$(grep -oP '(?<=void )\w+(?=\()' "$f" | tail -1 || true)
      if [ -z "$entry" ]; then
        skip "$f" "no entry point found"
        continue
      fi
      check "$f" ${PASS_FLAGS} -entry "$entry" -stage compute
    fi
  done <<< "$shaders"

  echo ""
done

# ===========================================================================
# Summary
# ===========================================================================
TOTAL=$((PASS + FAIL))
echo "=== Results: ${PASS} passed, ${FAIL} failed, ${SKIP} skipped (${TOTAL} compiled) ==="
echo "" >> "$RESULTS"
echo "Total: ${PASS} passed, ${FAIL} failed, ${SKIP} skipped" >> "$RESULTS"

if [ "$FAIL" -gt 0 ]; then
  echo ""
  printf "${RED}Shader compilation failed — see errors above.${NC}\n"
  exit 1
fi

echo ""
echo "All shaders compiled successfully."
