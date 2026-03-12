#!/usr/bin/env bash
# download_scenes.sh — Download test scenes for VisCache paper experiments.
#
# Usage:
#     ./scripts/download_scenes.sh [--dir <path>]
#
# Default download directory: media/
# Sets FALCOR_MEDIA_FOLDERS for the current session.
#
# Scenes:
#   - Arcade (bundled with Falcor, copied from Falcor/media/)
#   - Bistro (Amazon Lumberyard, NVIDIA ORCA)
#   - Sponza (Crytek, NVIDIA ORCA)
#   - Cornell Box (bundled with Falcor test_scenes)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MEDIA_DIR="${ROOT_DIR}/media"

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dir) MEDIA_DIR="$2"; shift 2 ;;
        *) echo "Usage: $0 [--dir <path>]"; exit 1 ;;
    esac
done

mkdir -p "$MEDIA_DIR"
echo "[scenes] Download directory: $MEDIA_DIR"

# ---------------------------------------------------------------------------
# Helper: download and extract a zip from a URL
# ---------------------------------------------------------------------------
download_and_extract() {
    local name="$1"
    local url="$2"
    local dest="$MEDIA_DIR/$name"

    if [ -d "$dest" ]; then
        echo "[scenes] $name already exists, skipping"
        return 0
    fi

    echo "[scenes] Downloading $name..."
    local tmpzip
    tmpzip="$(mktemp /tmp/${name}.XXXXXX.zip)"

    if command -v wget >/dev/null 2>&1; then
        wget -q --show-progress -O "$tmpzip" "$url"
    elif command -v curl >/dev/null 2>&1; then
        curl -fSL --progress-bar -o "$tmpzip" "$url"
    else
        echo "[scenes] ERROR: neither wget nor curl found" >&2
        return 1
    fi

    echo "[scenes] Extracting $name..."
    mkdir -p "$dest"
    unzip -q -o "$tmpzip" -d "$dest"
    rm -f "$tmpzip"
    echo "[scenes] $name ready at $dest"
}

# ---------------------------------------------------------------------------
# 1. Arcade — bundled with Falcor
# ---------------------------------------------------------------------------
if [ -d "$ROOT_DIR/Falcor/media/Arcade" ]; then
    if [ ! -d "$MEDIA_DIR/Arcade" ]; then
        echo "[scenes] Copying Arcade from Falcor/media/..."
        cp -r "$ROOT_DIR/Falcor/media/Arcade" "$MEDIA_DIR/Arcade"
    else
        echo "[scenes] Arcade already exists, skipping"
    fi
else
    echo "[scenes] WARNING: Falcor/media/Arcade not found — run setup first"
fi

# ---------------------------------------------------------------------------
# 2. Cornell Box — from Falcor test_scenes
# ---------------------------------------------------------------------------
if [ -d "$ROOT_DIR/Falcor/media/TestScenes" ]; then
    if [ ! -d "$MEDIA_DIR/TestScenes" ]; then
        echo "[scenes] Copying TestScenes from Falcor/media/..."
        cp -r "$ROOT_DIR/Falcor/media/TestScenes" "$MEDIA_DIR/TestScenes"
    else
        echo "[scenes] TestScenes already exists, skipping"
    fi
fi

# ---------------------------------------------------------------------------
# 3. Bistro (Amazon Lumberyard / NVIDIA ORCA)
#    NOTE: NVIDIA ORCA scenes require manual download due to EULA.
#    This downloads from the publicly mirrored Morgan McGuire archive.
# ---------------------------------------------------------------------------
BISTRO_URL="https://casual-effects.com/g3d/data10/research/model/Amazon_Lumberyard_Bistro/Bistro_v5_2.zip"

if [ ! -d "$MEDIA_DIR/Bistro" ]; then
    echo ""
    echo "[scenes] === Bistro (Amazon Lumberyard) ==="
    echo "[scenes] Source: casual-effects.com (Morgan McGuire mirror)"
    echo "[scenes] Size: ~3.2 GB compressed"
    echo ""
    read -rp "[scenes] Download Bistro? [y/N] " yn
    case "$yn" in
        [Yy]*)
            download_and_extract "Bistro" "$BISTRO_URL"
            # Create a convenience .pyscene wrapper if one doesn't exist
            if [ ! -f "$MEDIA_DIR/Bistro/Bistro_Interior.pyscene" ]; then
                cat > "$MEDIA_DIR/Bistro/Bistro_Interior.pyscene" << 'PYSCENE'
# Bistro Interior — convenience wrapper for VisCache experiments
import falcor
sceneBuilder = SceneBuilder()
sceneBuilder.importScene('BistroInterior.fbx')
PYSCENE
                echo "[scenes] Created Bistro_Interior.pyscene wrapper"
            fi
            ;;
        *) echo "[scenes] Skipping Bistro" ;;
    esac
else
    echo "[scenes] Bistro already exists, skipping"
fi

# ---------------------------------------------------------------------------
# 4. Sponza (Crytek / NVIDIA ORCA)
# ---------------------------------------------------------------------------
SPONZA_URL="https://casual-effects.com/g3d/data10/common/model/CrytekSponza/sponza.zip"

if [ ! -d "$MEDIA_DIR/Sponza" ]; then
    echo ""
    echo "[scenes] === Sponza (Crytek) ==="
    echo "[scenes] Source: casual-effects.com (Morgan McGuire mirror)"
    echo "[scenes] Size: ~70 MB compressed"
    echo ""
    read -rp "[scenes] Download Sponza? [y/N] " yn
    case "$yn" in
        [Yy]*)
            download_and_extract "Sponza" "$SPONZA_URL"
            if [ ! -f "$MEDIA_DIR/Sponza/Sponza.pyscene" ]; then
                cat > "$MEDIA_DIR/Sponza/Sponza.pyscene" << 'PYSCENE'
# Crytek Sponza — convenience wrapper for VisCache experiments
import falcor
sceneBuilder = SceneBuilder()
sceneBuilder.importScene('sponza.obj')
PYSCENE
                echo "[scenes] Created Sponza.pyscene wrapper"
            fi
            ;;
        *) echo "[scenes] Skipping Sponza" ;;
    esac
else
    echo "[scenes] Sponza already exists, skipping"
fi

# ---------------------------------------------------------------------------
# 5. VeachAjar — Benedikt Bitterli's rendering resources
#    Used by ReSTIRPTPass demo (DQLin's .pyscene wrappers are in the repo).
#    Source: https://benedikt-bitterli.me/resources/
# ---------------------------------------------------------------------------
VEACHAJAR_URL="https://benedikt-bitterli.me/resources/veach-ajar.zip"
VEACHAJAR_DEST="$ROOT_DIR/Source/RenderPasses/ReSTIRPTPass/Data/VeachAjar"

if [ -d "$VEACHAJAR_DEST/models" ] && [ -d "$VEACHAJAR_DEST/textures" ]; then
    echo "[scenes] VeachAjar already exists, skipping"
else
    echo ""
    echo "[scenes] === VeachAjar (Benedikt Bitterli) ==="
    echo "[scenes] Source: benedikt-bitterli.me/resources"
    echo "[scenes] Size: ~62 MB (models + textures)"
    echo "[scenes] Destination: Source/RenderPasses/ReSTIRPTPass/Data/VeachAjar/"
    echo ""
    read -rp "[scenes] Download VeachAjar? [y/N] " yn
    case "$yn" in
        [Yy]*)
            echo "[scenes] Downloading VeachAjar..."
            VEACH_TMPZIP="$(mktemp /tmp/veach-ajar.XXXXXX.zip)"

            if command -v wget >/dev/null 2>&1; then
                wget -q --show-progress -O "$VEACH_TMPZIP" "$VEACHAJAR_URL"
            elif command -v curl >/dev/null 2>&1; then
                curl -fSL --progress-bar -o "$VEACH_TMPZIP" "$VEACHAJAR_URL"
            else
                echo "[scenes] ERROR: neither wget nor curl found" >&2
                rm -f "$VEACH_TMPZIP"
                exit 1
            fi

            echo "[scenes] Extracting VeachAjar..."
            VEACH_TMPDIR="$(mktemp -d /tmp/veach-ajar.XXXXXX)"
            unzip -q -o "$VEACH_TMPZIP" -d "$VEACH_TMPDIR"

            # Bitterli's zip contains meshes/ and textures/ under a top-level dir.
            # Find the extracted root (may be veach-ajar/ or flat).
            VEACH_SRCDIR="$VEACH_TMPDIR"
            if [ -d "$VEACH_TMPDIR/veach-ajar" ]; then
                VEACH_SRCDIR="$VEACH_TMPDIR/veach-ajar"
            elif [ -d "$VEACH_TMPDIR/VeachAjar" ]; then
                VEACH_SRCDIR="$VEACH_TMPDIR/VeachAjar"
            fi

            # Copy models (meshes)
            mkdir -p "$VEACHAJAR_DEST/models"
            if [ -d "$VEACH_SRCDIR/meshes" ]; then
                cp -r "$VEACH_SRCDIR/meshes/"* "$VEACHAJAR_DEST/models/"
            elif [ -d "$VEACH_SRCDIR/models" ]; then
                cp -r "$VEACH_SRCDIR/models/"* "$VEACHAJAR_DEST/models/"
            else
                echo "[scenes] WARNING: Could not find meshes dir in zip — check structure"
                echo "[scenes] Extracted contents:" && ls -R "$VEACH_TMPDIR" | head -40
            fi

            # Copy textures
            mkdir -p "$VEACHAJAR_DEST/textures"
            if [ -d "$VEACH_SRCDIR/textures" ]; then
                cp -r "$VEACH_SRCDIR/textures/"* "$VEACHAJAR_DEST/textures/"
            fi

            rm -rf "$VEACH_TMPZIP" "$VEACH_TMPDIR"
            echo "[scenes] VeachAjar ready at $VEACHAJAR_DEST"
            echo "[scenes] Note: .pyscene wrappers (DQLin/Falcor format) are in the repo."
            ;;
        *) echo "[scenes] Skipping VeachAjar" ;;
    esac
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "[scenes] === Available scenes ==="
for d in "$MEDIA_DIR"/*/; do
    [ -d "$d" ] && echo "  $(basename "$d")"
done

echo ""
echo "[scenes] Set FALCOR_MEDIA_FOLDERS to use with Mogwai:"
echo "  export FALCOR_MEDIA_FOLDERS=\"$MEDIA_DIR\""
echo ""
echo "[scenes] Or pass --scene with full path:"
echo "  Mogwai.exe --scene \"$MEDIA_DIR/Bistro/Bistro_Interior.pyscene\""
