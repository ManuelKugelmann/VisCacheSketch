#!/usr/bin/env bash
# sync.sh — Sync shaders and data from source to runtime/.
#
# Shaders and data must be present in runtime/ for the shader compiler and
# scene importers. Scripts and scenes are served directly from source via
# PROJECT_ROOT search paths (source mode) — use --synced to also copy them.
#
# Usage: .scripts/sync_to_runtime.sh [--synced]
#   --synced  Also sync scenes/ and scripts/ to runtime/ (for CI / synced mode)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNTIME="$PROJECT_ROOT/runtime"

SYNC_SCRIPTS_SCENES=0
if [ "${1:-}" = "--synced" ]; then
    SYNC_SCRIPTS_SCENES=1
fi

# --- Shaders: Falcor core ---
FALCOR_SRC="$PROJECT_ROOT/Falcor/Source/Falcor"
if [ -d "$FALCOR_SRC" ]; then
    find "$FALCOR_SRC" -name "*.slang" -print0 | while IFS= read -r -d '' src; do
        rel="${src#$FALCOR_SRC/}"
        dst="$RUNTIME/shaders/$rel"
        mkdir -p "$(dirname "$dst")"
        cp -f "$src" "$dst"
    done
fi

# --- Shaders: our plugins (source of truth in Source/) ---
for pass in VisCache ReSTIRPTPass ReSTIRPTReferencePass ReSTIRDIPass ReSTIRDIReferencePass ReSTIRNEEPass PathTracerX PathTraceCommon CacheCommon ReSTIRCommon; do
    PASS_SRC="$PROJECT_ROOT/Source/RenderPasses/$pass"
    PASS_DST="$RUNTIME/shaders/RenderPasses/$pass"
    if [ -d "$PASS_SRC" ]; then
        mkdir -p "$PASS_DST"
        find "$PASS_SRC" -name "*.slang" -exec cp -f {} "$PASS_DST/" \;
    fi
done

# --- Shaders: Falcor render passes we modify (PathTracer, MinimalPathTracer, RTXDIPass) ---
# Preserve subdir structure (e.g. PathTracer/restirpt/PathState.slang must NOT
# clobber PathTracer/PathState.slang). The earlier `find ... -exec cp $src $DST/`
# was flattening — both PathState.slang's collapsed onto one path, restirpt
# version winning by alphabetical order, breaking Cornell-scene shader compiles.
FALCOR_PASSES="$PROJECT_ROOT/Falcor/Source/RenderPasses"
for pass in PathTracer MinimalPathTracer RTXDIPass; do
    PASS_SRC="$FALCOR_PASSES/$pass"
    PASS_DST="$RUNTIME/shaders/RenderPasses/$pass"
    if [ -d "$PASS_SRC" ]; then
        mkdir -p "$PASS_DST"
        # cd into PASS_SRC so `find .` returns relative paths; preserve subdirs.
        (
            cd "$PASS_SRC" || exit 0
            find . \( -name "*.slang" -o -name "*.slangh" \) -print0 \
                | while IFS= read -r -d '' rel; do
                    rel="${rel#./}"
                    mkdir -p "$PASS_DST/$(dirname "$rel")"
                    cp -f "$PASS_SRC/$rel" "$PASS_DST/$rel"
                done
        )
    fi
done

# --- Data: plugin data files ---
DATA_SRC="$PROJECT_ROOT/Source/RenderPasses/ReSTIRPTPass/Data"
DATA_DST="$RUNTIME/data/ReSTIRPTPass"
if [ -d "$DATA_SRC" ]; then
    mkdir -p "$DATA_DST"
    cp -rf "$DATA_SRC/"* "$DATA_DST/"
fi

# --- Scenes + Scripts: only in --synced mode (CI). ---
# In source mode, mogwai-headless/headed.sh serve these from source via PROJECT_ROOT.
if [ "$SYNC_SCRIPTS_SCENES" -eq 1 ]; then
    SCENES_SRC="$PROJECT_ROOT/scenes"
    SCENES_DST="$RUNTIME/media/scenes"
    if [ -d "$SCENES_SRC" ]; then
        mkdir -p "$SCENES_DST"
        cp -f "$SCENES_SRC/"*.pyscene "$SCENES_SRC/"*.py "$SCENES_DST/" 2>/dev/null
    fi

    SCRIPTS_SRC="$PROJECT_ROOT/scripts"
    SCRIPTS_DST="$RUNTIME/scripts/VisCache"
    if [ -d "$SCRIPTS_SRC" ]; then
        mkdir -p "$SCRIPTS_DST"
        cp -rf "$SCRIPTS_SRC/"* "$SCRIPTS_DST/"
    fi
    echo "[sync] Scenes and scripts synced to runtime/ (synced mode)"
fi

# --- Clear shader cache ---
if [ -d "$RUNTIME/.shadercache" ]; then
    find "$RUNTIME/.shadercache" -not -name lock -not -path "$RUNTIME/.shadercache" -delete 2>/dev/null
    rm -f "$RUNTIME/.shadercache/index" 2>/dev/null
    echo "[sync] Shader cache cleared"
fi

# --- Validate binaries ---
BUILD_OUT="$PROJECT_ROOT/Falcor/build/windows-vs2022/bin/Release"
if [ -f "$BUILD_OUT/Mogwai.exe" ] && [ -f "$RUNTIME/Mogwai.exe" ]; then
    BUILD_TS=$(stat -c %Y "$BUILD_OUT/Mogwai.exe" 2>/dev/null || echo 0)
    RUNTIME_TS=$(stat -c %Y "$RUNTIME/Mogwai.exe" 2>/dev/null || echo 0)
    if [ "$BUILD_TS" -gt "$RUNTIME_TS" ]; then
        echo -e "[sync] \033[33mWARNING: runtime binaries are older than build output — rebuild or copy manually\033[0m"
    fi
fi

echo "[sync] Shaders and data synced to runtime/"
