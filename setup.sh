#!/bin/bash
# setup.sh — MLVHF Falcor 8.0 integration setup script (Linux)
# Run from the MLVHF package root: ./setup.sh
#
# What this script does:
#   1. Locates Falcor (Falcor subtree or FALCOR_ROOT override)
#   2. Populates Falcor internal submodules (if empty after subtree squash)
#   3. Copies MLVHF source files into the Falcor tree
#   4. Patches CMakeLists.txt to register the plugins
#   5. Runs the Python unit tests
#
# Usage:
#   ./setup.sh                              # use bundled subtree
#   FALCOR_ROOT=/path/to/falcor ./setup.sh  # use external Falcor
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

log()  { echo -e "\033[36m[MLVHF]\033[0m $1"; }
fail() { echo -e "\033[31m[MLVHF] ERROR:\033[0m $1"; exit 1; }

# ---------------------------------------------------------------------------
# Step 1: Resolve Falcor root
# ---------------------------------------------------------------------------
FALCOR_ROOT="${FALCOR_ROOT:-${SCRIPT_DIR}/Falcor}"
log "Step 1: Using Falcor at: ${FALCOR_ROOT}"

[ -f "${FALCOR_ROOT}/CMakeLists.txt" ] || fail "CMakeLists.txt not found in ${FALCOR_ROOT}"

# ---------------------------------------------------------------------------
# Step 2: Populate Falcor internal submodules (subtree fixup)
# ---------------------------------------------------------------------------
log "Step 2: Checking Falcor internal submodules..."

declare -A SUBMODS=(
    [pybind11]="https://github.com/skallweitNV/pybind11.git"
    [glfw]="https://github.com/glfw/glfw.git"
    [args]="https://github.com/Taywee/args.git"
    [fmt]="https://github.com/fmtlib/fmt.git"
    [imgui]="https://github.com/ocornut/imgui.git"
    [vulkan-headers]="https://github.com/KhronosGroup/Vulkan-Headers.git"
)

for name in "${!SUBMODS[@]}"; do
    dir="${FALCOR_ROOT}/external/${name}"
    url="${SUBMODS[$name]}"
    # Check if directory is empty or missing key files
    if [ ! -f "${dir}/CMakeLists.txt" ] && [ ! -f "${dir}/imgui.h" ]; then
        log "  Cloning ${name}..."
        rm -rf "${dir}"
        git clone --depth 1 "${url}" "${dir}"
    else
        log "  ${name}: already populated"
    fi
done

# ---------------------------------------------------------------------------
# Step 3: Copy MLVHF sources into Falcor tree
# ---------------------------------------------------------------------------
log "Step 3: Copying MLVHF RenderPass sources..."

# VisHashFilter
VHF_DST="${FALCOR_ROOT}/Source/RenderPasses/VisHashFilter"
mkdir -p "${VHF_DST}"
cp -r "${SCRIPT_DIR}/Source/RenderPasses/VisHashFilter/"* "${VHF_DST}/"
log "  Copied: VisHashFilter"

# ReSTIRGIPass
GI_DST="${FALCOR_ROOT}/Source/RenderPasses/ReSTIRGIPass"
mkdir -p "${GI_DST}"
cp -r "${SCRIPT_DIR}/Source/RenderPasses/ReSTIRGIPass/"* "${GI_DST}/"
log "  Copied: ReSTIRGIPass"

# Scripts
SCRIPT_DST="${FALCOR_ROOT}/scripts/MLVHF"
mkdir -p "${SCRIPT_DST}"
cp -r "${SCRIPT_DIR}/scripts/"* "${SCRIPT_DST}/"
log "  Copied: scripts"

# Tests
TEST_DST="${FALCOR_ROOT}/scripts/MLVHF/tests"
mkdir -p "${TEST_DST}"
cp -r "${SCRIPT_DIR}/tests/"* "${TEST_DST}/"
log "  Copied: tests"

# ---------------------------------------------------------------------------
# Step 4: Patch CMakeLists.txt to register plugins
# ---------------------------------------------------------------------------
log "Step 4: Patching Source/RenderPasses/CMakeLists.txt..."

RP_CMAKE="${FALCOR_ROOT}/Source/RenderPasses/CMakeLists.txt"
[ -f "${RP_CMAKE}" ] || fail "Could not find ${RP_CMAKE}"

if ! grep -q "add_subdirectory(VisHashFilter)" "${RP_CMAKE}"; then
    echo "add_subdirectory(VisHashFilter)" >> "${RP_CMAKE}"
    log "  Added: add_subdirectory(VisHashFilter)"
else
    log "  Already present: VisHashFilter (skipped)"
fi

if ! grep -q "add_subdirectory(ReSTIRGIPass)" "${RP_CMAKE}"; then
    echo "add_subdirectory(ReSTIRGIPass)" >> "${RP_CMAKE}"
    log "  Added: add_subdirectory(ReSTIRGIPass)"
else
    log "  Already present: ReSTIRGIPass (skipped)"
fi

# ---------------------------------------------------------------------------
# Step 5: Run Python unit tests
# ---------------------------------------------------------------------------
log "Step 5: Running CPU unit tests..."
python3 "${SCRIPT_DIR}/tests/test_vhf_convergence.py"
log "  All unit tests passed."

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
log "Setup complete."
echo ""
echo "Next steps:"
echo "  1. Fetch packman deps: cd ${FALCOR_ROOT} && ./tools/packman/packman pull --platform linux-x86_64 dependencies.xml"
echo "  2. Configure:  cd ${FALCOR_ROOT} && ./tools/.packman/cmake/bin/cmake --preset linux-gcc"
echo "  3. Build:      cd ${FALCOR_ROOT} && ./tools/.packman/cmake/bin/cmake --build build/linux-gcc --config Release"
echo ""
