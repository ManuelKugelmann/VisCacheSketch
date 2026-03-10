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
