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
# Falcor defines from slang-ci-defines.slangh are injected via -D flags.
#
# Usage: scripts/slang-ci-check.sh <path-to-slangc>
#
# Three tiers:
#   Tier 1 — Self-contained VisCache core (no Falcor deps).
#            Failures block the PR.
#   Tier 2 — VisCache shaders with Falcor imports (Scene.*, Utils.*).
#            Compiled with default Falcor defines + CI stubs.
#            Failures block the PR.
#   Tier 3 — ReSTIRPTPass shaders (deep Falcor scene system deps).
#            Best-effort: reported but do not block.

set -euo pipefail

SLANGC="${1:?Usage: $0 <path-to-slangc>}"
RESULTS="slang-check-results.log"
: > "$RESULTS"

# slangc SPIR-V backend cannot write to /dev/null — use a real temp file.
TMPOUT="$(mktemp /tmp/slang-ci-XXXXXX.spv)"
trap 'rm -f "$TMPOUT"' EXIT

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
    if [ "$tier" = "3" ]; then
      printf "${YELLOW}SKIP${NC} (${label})\n"
      echo "SKIP $file ($label)" >> "$RESULTS"
      SKIP=$((SKIP + 1))
    else
      printf "${RED}FAIL${NC} (tier ${tier})\n"
      echo "FAIL $file" >> "$RESULTS"
      echo "$output" >> "$RESULTS"
      echo "$output" >&2
      FAIL=$((FAIL + 1))
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
# Include paths — mirrors Falcor ProgramManager's getInitialShaderDirectories
# ---------------------------------------------------------------------------
SEARCH_PATHS="-I ${FALCOR}/Source/Falcor -I ${FALCOR}/Source -I ${FALCOR}/external/packman/nanovdb/include"

# Tier 1: self-contained, no defines needed
VISCACHE_DIR="${FALCOR}/Source/RenderPasses/VisCache"
T1_FLAGS="-target spirv -I ${VISCACHE_DIR}"

# Tier 2: Falcor imports + defines + stubs
T2_FLAGS="-target spirv ${SEARCH_PATHS} ${DFLAGS}"
STUBS="${SCRIPT_DIR}/slang-ci-stubs.slang"

# ---------------------------------------------------------------------------
# Tier 1: Self-contained VisCache core
# ---------------------------------------------------------------------------
echo "--- Tier 1: VisCache core (self-contained) ---"

# Library module (no entry point)
check "${VISCACHE_DIR}/VisCache.slang" 1 "" \
  -target spirv -o "$TMPOUT"

# Compute shaders with entry points
check "${VISCACHE_DIR}/VisCacheInsert.cs.slang" 1 "" \
  ${T1_FLAGS} -entry csInsert -stage compute -o "$TMPOUT"

check "${VISCACHE_DIR}/VisCacheDecay.cs.slang" 1 "" \
  ${T1_FLAGS} -entry csDecay -stage compute -o "$TMPOUT"

echo ""

# ---------------------------------------------------------------------------
# Tier 2: VisCache shaders with Falcor dependencies
# ---------------------------------------------------------------------------
echo "--- Tier 2: VisCache Falcor-dependent shaders ---"

check "${VISCACHE_DIR}/VisCacheTracing.slang" 2 "" \
  ${T2_FLAGS} -o "$TMPOUT" "${STUBS}"

check "${VISCACHE_DIR}/ShadingCV.slang" 2 "" \
  ${T2_FLAGS} -o "$TMPOUT" "${STUBS}"

check "${VISCACHE_DIR}/RevalidationCommon.slang" 2 "" \
  ${T2_FLAGS} -o "$TMPOUT" "${STUBS}"

echo ""

# ---------------------------------------------------------------------------
# Tier 3: ReSTIRPTPass shaders (best-effort)
# ---------------------------------------------------------------------------
echo "--- Tier 3: ReSTIRPTPass shaders (best-effort) ---"

RESTIR_DIR="${FALCOR}/Source/RenderPasses/ReSTIRPTPass"
if [ -d "$RESTIR_DIR" ]; then
  for f in "$RESTIR_DIR"/*.cs.slang; do
    [ -f "$f" ] || continue
    # Extract entry point name (first function after [numthreads])
    entry=$(grep -oP '(?<=void )\w+(?=\()' "$f" | head -1 || true)
    if [ -n "$entry" ]; then
      check "$f" 3 "ReSTIRPTPass deep deps" \
        ${T2_FLAGS} -I "${RESTIR_DIR}" -entry "$entry" -stage compute -o "$TMPOUT" "${STUBS}"
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
  printf "${RED}Shader compilation failed — see errors above.${NC}\n"
  exit 1
fi

echo ""
echo "All blocking shaders (Tier 1 + Tier 2) compiled successfully."
