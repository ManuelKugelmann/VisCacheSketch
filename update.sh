#!/usr/bin/env bash
# update.sh — Pull latest + download release + deploy shaders/data.
#
# Usage:  ./update.sh [--skip-scenes]
#
# For the full flow (tests + smoke test + launch), use ./quickstart.sh instead.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RELEASE_DIR="$SCRIPT_DIR/release"
MEDIA_DIR="$RELEASE_DIR/media"
SKIP_SCENES=0

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-scenes) SKIP_SCENES=1; shift ;;
        *) echo "Usage: $0 [--skip-scenes]"; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Step 1: Pull latest
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo " Step 1: Pull latest changes"
echo "========================================"
BRANCH="$(git -C "$SCRIPT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
if [ -n "$BRANCH" ]; then
    echo "[update] branch: $BRANCH"
    git -C "$SCRIPT_DIR" pull origin "$BRANCH" || echo "[update] WARNING: pull failed, continuing with current checkout"
else
    echo "[update] not a git repo, skipping pull"
fi

# ---------------------------------------------------------------------------
# Step 2: Download release
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo " Step 2: Download latest release"
echo "========================================"
bash "$SCRIPT_DIR/scripts/download_release.sh"

# ---------------------------------------------------------------------------
# Step 3: Download scenes
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo " Step 3: Download scenes"
echo "========================================"
if [ "$SKIP_SCENES" -eq 1 ]; then
    echo "[update] skipping scene download (--skip-scenes)"
else
    bash "$SCRIPT_DIR/scripts/download_scenes.sh" || echo "[update] WARNING: Some scenes failed to download"
fi

# ---------------------------------------------------------------------------
# Step 4: Deploy shaders, data, scripts to release
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo " Step 4: Deploy shaders and data"
echo "========================================"
if [ -d "$RELEASE_DIR" ]; then
    # Deploy Falcor built-in shaders
    FALCOR_SRC="$SCRIPT_DIR/Falcor/Source/Falcor"
    FALCOR_DST="$RELEASE_DIR/shaders"
    if [ -d "$FALCOR_SRC" ]; then
        find "$FALCOR_SRC" -name "*.slang" | while read -r f; do
            REL="${f#"$FALCOR_SRC"/}"
            mkdir -p "$FALCOR_DST/$(dirname "$REL")"
            cp "$f" "$FALCOR_DST/$REL"
        done
        echo "[update]   Falcor built-in shaders deployed"
    fi

    # Custom render pass shaders
    for PASS in VisCache ReSTIRPTPass; do
        SRC="$SCRIPT_DIR/Source/RenderPasses/$PASS"
        DST="$RELEASE_DIR/shaders/RenderPasses/$PASS"
        if [ -d "$SRC" ]; then
            mkdir -p "$DST"
            find "$SRC" -name "*.slang" -exec cp {} "$DST/" \;
            echo "[update]   $PASS shaders deployed"
        fi
    done

    # Deploy scripts
    SCRIPTS_SRC="$SCRIPT_DIR/scripts"
    SCRIPTS_DST="$RELEASE_DIR/scripts/VisCache"
    if [ -f "$SCRIPTS_SRC/smoke_test.py" ]; then
        mkdir -p "$SCRIPTS_DST"
        cp -r "$SCRIPTS_SRC/"* "$SCRIPTS_DST/"
        echo "[update]   scripts deployed"
    fi

    # Deploy ReSTIRPTPass data files
    DATA_SRC="$SCRIPT_DIR/Source/RenderPasses/ReSTIRPTPass/Data"
    DATA_DST="$RELEASE_DIR/data/ReSTIRPTPass"
    if [ -f "$DATA_SRC/16RooksPattern256.txt" ]; then
        mkdir -p "$DATA_DST"
        cp -r "$DATA_SRC/"* "$DATA_DST/"
        echo "[update]   ReSTIRPTPass data deployed"
    fi

    # Validate shaders
    if command -v python3 &>/dev/null; then
        python3 "$SCRIPT_DIR/scripts/validate_shaders.py" --root-dir "$SCRIPT_DIR" --release-dir "$RELEASE_DIR" || \
            echo "[update] WARNING: Shader validation found issues"
    fi
else
    echo "[update] no release found — skipping deploy"
fi

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "[update] Done. Run ./quickstart.sh to also run tests and launch."
