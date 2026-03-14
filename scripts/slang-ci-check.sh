#!/usr/bin/env bash
# slang-ci-check.sh — Offline Slang shader compilation for CI.
#
# Mimics the include-path setup that Falcor's ProgramManager uses at runtime
# (see Falcor/Source/Falcor/Core/Platform/OS.cpp getInitialShaderDirectories):
#   1. <project>/Source/Falcor   (Scene.*, Utils.*, Rendering.*)
#   2. <project>/Source          (RenderPasses.*)
#
# We copy our render passes into the Falcor tree (same as build.yml) so that
# import paths like `RenderPasses.VisCache.VisCache` resolve correctly.
#
# Usage: scripts/slang-ci-check.sh <path-to-slangc>
#
# Two tiers:
#   Tier 1 — Self-contained VisCache core (no Falcor deps).
#            These always compile; failures block the PR.
#   Tier 2 — Files importing Falcor modules (Scene.*, Utils.*, etc.).
#            Best-effort: reported but do not block, since Falcor normally
#            injects host-side defines (SCENE_GEOMETRY_TYPES etc.) that
#            are unavailable without a full CMake configure + build.

set -euo pipefail

SLANGC="${1:?Usage: $0 <path-to-slangc>}"
RESULTS="slang-check-results.log"
: > "$RESULTS"

PASS=0
FAIL=0
SKIP=0

# Colours (CI-friendly: only when stdout is a terminal)
if [ -t 1 ]; then
  GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[0;33m'; NC='\033[0m'
else
  GREEN=''; RED=''; YELLOW=''; NC=''
fi

check() {
  local file="$1"; shift
  local tier="$1"; shift
  local label="$1"; shift

  printf "  %-55s " "$file"

  # shellcheck disable=SC2068
  if output=$("$SLANGC" $@ "$file" 2>&1); then
    printf "${GREEN}OK${NC}\n"
    echo "OK   $file" >> "$RESULTS"
    PASS=$((PASS + 1))
  else
    if [ "$tier" = "1" ]; then
      printf "${RED}FAIL${NC}\n"
      echo "FAIL $file" >> "$RESULTS"
      echo "$output" >> "$RESULTS"
      echo "$output" >&2
      FAIL=$((FAIL + 1))
    else
      printf "${YELLOW}SKIP${NC} (${label})\n"
      echo "SKIP $file ($label)" >> "$RESULTS"
      SKIP=$((SKIP + 1))
    fi
  fi
}

echo "=== Slang Shader CI Check ==="
echo ""

# ---------------------------------------------------------------------------
# Setup: copy render passes into Falcor tree (same as build.yml)
# This makes `import RenderPasses.VisCache.VisCache` resolve correctly.
# ---------------------------------------------------------------------------
FALCOR="Falcor"
echo "Integrating render passes into Falcor source tree..."
mkdir -p "${FALCOR}/Source/RenderPasses/VisCache"
cp -r Source/RenderPasses/VisCache/* "${FALCOR}/Source/RenderPasses/VisCache/"
mkdir -p "${FALCOR}/Source/RenderPasses/ReSTIRPTPass"
cp -r Source/RenderPasses/ReSTIRPTPass/* "${FALCOR}/Source/RenderPasses/ReSTIRPTPass/"
echo ""

# ---------------------------------------------------------------------------
# Include paths — mirrors Falcor ProgramManager's getInitialShaderDirectories
# ---------------------------------------------------------------------------
SEARCH_PATHS="-I ${FALCOR}/Source/Falcor -I ${FALCOR}/Source"

# Common flags for all compilations
COMMON="-target spirv ${SEARCH_PATHS}"

# Tier 1 VisCache directory (for relative `import VisCache`)
VISCACHE_DIR="${FALCOR}/Source/RenderPasses/VisCache"
T1_FLAGS="${COMMON} -I ${VISCACHE_DIR}"

# ---------------------------------------------------------------------------
# Tier 1: Self-contained VisCache core
# ---------------------------------------------------------------------------
echo "--- Tier 1: VisCache core (self-contained) ---"

# Library module (no entry point)
check "${VISCACHE_DIR}/VisCache.slang" 1 "" \
  -target spirv -o /dev/null

# Compute shaders with entry points
check "${VISCACHE_DIR}/VisCacheInsert.cs.slang" 1 "" \
  ${T1_FLAGS} -entry csInsert -stage compute -o /dev/null

check "${VISCACHE_DIR}/VisCacheDecay.cs.slang" 1 "" \
  ${T1_FLAGS} -entry csDecay -stage compute -o /dev/null

echo ""

# ---------------------------------------------------------------------------
# Tier 2: Files with Falcor dependencies (best-effort)
# ---------------------------------------------------------------------------
echo "--- Tier 2: Falcor-dependent shaders (best-effort) ---"

check "${VISCACHE_DIR}/ShadingCV.slang" 2 "needs Falcor ShadingData" \
  ${COMMON} -o /dev/null

check "${VISCACHE_DIR}/VisCacheTracing.slang" 2 "needs Scene.RaytracingInline" \
  ${COMMON} -o /dev/null

check "${VISCACHE_DIR}/RevalidationCommon.slang" 2 "needs Utils.Math" \
  ${COMMON} -o /dev/null

# ReSTIRPTPass entry-point shaders
RESTIR_DIR="${FALCOR}/Source/RenderPasses/ReSTIRPTPass"
if [ -d "$RESTIR_DIR" ]; then
  for f in "$RESTIR_DIR"/*.cs.slang; do
    [ -f "$f" ] || continue
    # Extract entry point name (first function after [numthreads])
    entry=$(grep -oP '(?<=void )\w+(?=\()' "$f" | head -1 || true)
    if [ -n "$entry" ]; then
      check "$f" 2 "needs Falcor scene system" \
        ${COMMON} -I "${RESTIR_DIR}" -entry "$entry" -stage compute -o /dev/null
    fi
  done
fi

echo ""

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
TOTAL=$((PASS + FAIL + SKIP))
echo "=== Results: ${PASS} passed, ${FAIL} failed, ${SKIP} skipped (${TOTAL} total) ==="
echo "" >> "$RESULTS"
echo "Total: ${PASS} passed, ${FAIL} failed, ${SKIP} skipped" >> "$RESULTS"

if [ "$FAIL" -gt 0 ]; then
  echo ""
  printf "${RED}Tier 1 shader compilation failed — see errors above.${NC}\n"
  exit 1
fi

echo ""
echo "All Tier 1 (self-contained) shaders compiled successfully."
