#!/bin/bash
# setup-build-system.sh — VisCache Falcor 8.0 integration setup script
# Run from the VisCache package root: ./setup-build-system.sh
#
# What this script does:
#   1. Locates Falcor (Falcor subtree or FALCOR_ROOT override)
#   2. Copies VisCache source files into the Falcor tree
#   3. Patches CMakeLists.txt to register the plugins
#   4. Calls Falcor's setup.sh (submodule init, packman deps, git hooks)
#   5. Runs the Python unit tests
#
# Usage:
#   ./setup-build-system.sh                              # use bundled subtree
#   FALCOR_ROOT=/path/to/falcor ./setup-build-system.sh  # use external Falcor
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

log()  { echo -e "\033[36m[VisCache]\033[0m $1"; }
fail() { echo -e "\033[31m[VisCache] ERROR:\033[0m $1"; exit 1; }

# Publish the project root so Falcor/setup.sh can find it without relying
# on fragile relative-path navigation.  Falcor is a subtree, not a standalone
# repo, so its setup script cannot know the git root on its own.
export VISCACHE_ROOT="${SCRIPT_DIR}"

# ---------------------------------------------------------------------------
# Step 1: Resolve Falcor root
# ---------------------------------------------------------------------------
FALCOR_ROOT="${FALCOR_ROOT:-${SCRIPT_DIR}/Falcor}"
log "Step 1: Using Falcor at: ${FALCOR_ROOT}"

[ -f "${FALCOR_ROOT}/CMakeLists.txt" ] || fail "CMakeLists.txt not found in ${FALCOR_ROOT}"

# ---------------------------------------------------------------------------
# Step 1b: Enable git hooks
# ---------------------------------------------------------------------------
if [ -d "${SCRIPT_DIR}/.githooks" ]; then
    git -C "${SCRIPT_DIR}" config core.hooksPath .githooks
    log "Step 1b: Enabled .githooks (pre-commit: submodule sync check)"
fi

# ---------------------------------------------------------------------------
# Steps 2-3: Plugin integration
# ---------------------------------------------------------------------------
# Plugins build in-place via FALCOR_PLUGIN_DIRS (no source copy needed).
# CMake patches are committed in the Falcor subtree.
# Scripts, data, and shaders are deployed by CMake POST_BUILD rules.
log "Steps 2-3: Plugin integration handled by CMake (no copy needed)"

# ---------------------------------------------------------------------------
# Step 4: Run Falcor's own setup (submodules + packman deps)
# ---------------------------------------------------------------------------
log "Step 4: Running Falcor setup (submodules + packman)..."

FALCOR_SETUP="${FALCOR_ROOT}/setup.sh"
if [ -x "${FALCOR_SETUP}" ] || [ -f "${FALCOR_SETUP}" ]; then
    bash "${FALCOR_SETUP}"
    log "  Falcor setup complete."
else
    log "  WARNING: ${FALCOR_SETUP} not found, skipping Falcor setup."
    log "  You may need to init submodules and fetch packman deps manually."
fi

# ---------------------------------------------------------------------------
# Step 5: Run Python unit tests
# ---------------------------------------------------------------------------
log "Step 5: Running CPU unit tests..."
python3 "${SCRIPT_DIR}/tests/test_viscache_convergence.py"
log "  All unit tests passed."

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
log "Setup complete."
echo ""
echo "Next steps:"
echo "  1. Configure:  cmake --preset linux-gcc-ci -S ${FALCOR_ROOT}"
echo "  2. Build:      cmake --build ${FALCOR_ROOT}/build/linux-gcc-ci --config Release"
echo ""
