#!/usr/bin/env bash
# sync.sh — Sync shaders, scripts, and data from source to runtime/.
#
# Use case: iterate on .slang shaders or .py scripts without a full rebuild.
# CMake handles this for full builds; this script is for hot-reload only.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNTIME="$PROJECT_ROOT/runtime"

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
for pass in VisCache ReSTIRPTPass; do
    PASS_SRC="$PROJECT_ROOT/Source/RenderPasses/$pass"
    PASS_DST="$RUNTIME/shaders/RenderPasses/$pass"
    if [ -d "$PASS_SRC" ]; then
        mkdir -p "$PASS_DST"
        find "$PASS_SRC" -name "*.slang" -exec cp -f {} "$PASS_DST/" \;
    fi
done

# --- Shaders: Falcor render passes we modify (PathTracer, MinimalPathTracer, RTXDIPass) ---
FALCOR_PASSES="$PROJECT_ROOT/Falcor/Source/RenderPasses"
for pass in PathTracer MinimalPathTracer RTXDIPass; do
    PASS_SRC="$FALCOR_PASSES/$pass"
    PASS_DST="$RUNTIME/shaders/RenderPasses/$pass"
    if [ -d "$PASS_SRC" ]; then
        mkdir -p "$PASS_DST"
        find "$PASS_SRC" -name "*.slang" -o -name "*.slangh" | while IFS= read -r src; do
            cp -f "$src" "$PASS_DST/"
        done
    fi
done

# --- Data: plugin data files ---
DATA_SRC="$PROJECT_ROOT/Source/RenderPasses/ReSTIRPTPass/Data"
DATA_DST="$RUNTIME/data/ReSTIRPTPass"
if [ -d "$DATA_SRC" ]; then
    mkdir -p "$DATA_DST"
    cp -rf "$DATA_SRC/"* "$DATA_DST/"
fi

# --- Scenes ---
SCENES_SRC="$PROJECT_ROOT/scenes"
SCENES_DST="$RUNTIME/media/scenes"
if [ -d "$SCENES_SRC" ]; then
    mkdir -p "$SCENES_DST"
    cp -f "$SCENES_SRC/"*.pyscene "$SCENES_SRC/"*.py "$SCENES_DST/" 2>/dev/null
fi

# --- Scripts ---
SCRIPTS_SRC="$PROJECT_ROOT/scripts"
SCRIPTS_DST="$RUNTIME/scripts/VisCache"
if [ -d "$SCRIPTS_SRC" ]; then
    mkdir -p "$SCRIPTS_DST"
    cp -rf "$SCRIPTS_SRC/"* "$SCRIPTS_DST/"
fi

# --- Clear shader cache ---
if [ -d "$RUNTIME/.shadercache" ]; then
    # Lock file may be held by a running Mogwai — delete everything except it.
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
        echo -e "[sync] \033[33mWARNING: runtime binaries are older than build output — rebuild with output redirect or copy manually\033[0m"
    fi
fi

echo "[sync] Shaders, scripts, and data synced to runtime/"
