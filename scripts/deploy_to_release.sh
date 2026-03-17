#!/usr/bin/env bash
# deploy_to_release.sh — Deploy shaders, scripts, and data from source tree to release/.
#
# Called by: quickstart.sh (step 3), run_release.sh (before launch).
# Idempotent: safe to re-run.
#
# Expects caller to set: ROOT_DIR, RELEASE_DIR

set -euo pipefail

if [ -z "${ROOT_DIR:-}" ] || [ -z "${RELEASE_DIR:-}" ]; then
    echo "[deploy] ERROR: ROOT_DIR and RELEASE_DIR must be set"
    exit 1
fi

# ---------------------------------------------------------------------------
# Deploy scripts from source tree into release/scripts/VisCache/
# ---------------------------------------------------------------------------
SCRIPTS_SRC="${ROOT_DIR}/scripts"
SCRIPTS_DST="${RELEASE_DIR}/scripts/VisCache"
if [ -f "$SCRIPTS_SRC/smoke_test.py" ]; then
    mkdir -p "$SCRIPTS_DST"
    cp -r "$SCRIPTS_SRC/"* "$SCRIPTS_DST/"
    echo "[deploy] Deployed fresh scripts from source tree to release/scripts/VisCache/"
fi

# ---------------------------------------------------------------------------
# Deploy data files (e.g. 16RooksPattern256.txt) into release/data/
# ---------------------------------------------------------------------------
DATA_SRC="${ROOT_DIR}/Source/RenderPasses/ReSTIRPTPass/Data"
DATA_DST="${RELEASE_DIR}/data/ReSTIRPTPass"
if [ ! -f "$DATA_DST/16RooksPattern256.txt" ]; then
    if [ -f "$DATA_SRC/16RooksPattern256.txt" ]; then
        mkdir -p "$DATA_DST"
        cp -r "$DATA_SRC/"* "$DATA_DST/"
        echo "[deploy] Deployed ReSTIRPTPass data files to release/data/"
    else
        echo "[deploy] WARNING: $DATA_SRC/16RooksPattern256.txt not found in source tree"
    fi
fi
if [ ! -f "$DATA_DST/16RooksPattern256.txt" ]; then
    echo "[deploy] WARNING: 16RooksPattern256.txt missing — ReSTIRPTPass will fail to load"
    echo "[deploy] Expected at: $DATA_DST/16RooksPattern256.txt"
fi

# ---------------------------------------------------------------------------
# Deploy shaders from source tree (source is always authoritative)
# ---------------------------------------------------------------------------
FALCOR_SRC="${ROOT_DIR}/Falcor/Source/Falcor"
if [ -d "$FALCOR_SRC" ]; then
    find "$FALCOR_SRC" -name "*.slang" -print0 | while IFS= read -r -d '' src; do
        rel="${src#$FALCOR_SRC/}"
        dst="${RELEASE_DIR}/shaders/${rel}"
        mkdir -p "$(dirname "$dst")"
        cp -f "$src" "$dst"
    done
fi
for pass in VisCache ReSTIRPTPass; do
    PASS_SRC="${ROOT_DIR}/Source/RenderPasses/${pass}"
    PASS_DST="${RELEASE_DIR}/shaders/RenderPasses/${pass}"
    if [ -d "$PASS_SRC" ]; then
        mkdir -p "$PASS_DST"
        find "$PASS_SRC" -name "*.slang" -exec cp -f {} "$PASS_DST/" \;
    fi
done
echo "[deploy] Shaders deployed from source tree"

# ---------------------------------------------------------------------------
# Validate NRD (denoiser) availability
# ---------------------------------------------------------------------------
NRD_OK=1
if [ ! -f "$RELEASE_DIR/NRDPass.dll" ]; then
    echo "[deploy]   NRDPass.dll: MISSING"
    NRD_OK=0
else
    echo "[deploy]   NRDPass.dll: OK"
fi
if [ ! -f "$RELEASE_DIR/NRD.dll" ]; then
    echo "[deploy]   NRD.dll: MISSING"
    NRD_OK=0
else
    echo "[deploy]   NRD.dll: OK"
fi
if [ "$NRD_OK" -eq 0 ]; then
    echo "[deploy]   WARNING: NRD denoiser not in release -- output will be raw noisy radiance."
    echo "[deploy]   Rebuild with D3D12 + packman NRD package, or download a release that includes NRD."
else
    echo "[deploy]   NRD denoiser: available"
fi

# ---------------------------------------------------------------------------
# Validate shaders (content hash)
# ---------------------------------------------------------------------------
PYTHON_CMD=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
fi
if [ -n "$PYTHON_CMD" ]; then
    "$PYTHON_CMD" "${ROOT_DIR}/scripts/validate_shaders.py" --root-dir "${ROOT_DIR}" --release-dir "${RELEASE_DIR}" || \
        echo "[deploy] WARNING: Shader validation found issues — see above"
else
    # Fallback: at least check sentinel
    if [ ! -f "${RELEASE_DIR}/shaders/Scene/Material/TextureSampler.slang" ]; then
        echo "[deploy] ERROR: Falcor shaders missing from release/shaders/ after deploy"
        exit 1
    fi
fi
