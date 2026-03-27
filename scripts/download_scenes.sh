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
#   - Rungholt (McGuire CG Archive, medieval town ~260m)
#   - Sun Temple (Epic Games / NVIDIA ORCA)
#   - Manhattan (Sketchfab, OSM city model ~21km — manual download)
#   - Cornell Box (bundled with Falcor test_scenes)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MEDIA_DIR="${ROOT_DIR}/runtime/media"

# shellcheck disable=SC1091
source "$SCRIPT_DIR/version.sh" "scenes" 2>/dev/null || true

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dir) MEDIA_DIR="$2"; shift 2 ;;
        *) echo "Usage: $0 [--dir <path>]"; exit 1 ;;
    esac
done

mkdir -p "$MEDIA_DIR"
echo "[scenes] Download directory: $MEDIA_DIR"

SCENES_DIR="${ROOT_DIR}/scenes"

# ---------------------------------------------------------------------------
# Helper: download and extract a zip from a URL
# If the zip contains a single top-level directory, flatten it so the
# contents end up directly under $MEDIA_DIR/$name.
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

    if command -v curl >/dev/null 2>&1; then
        curl -fSL --progress-bar -o "$tmpzip" "$url"
    elif command -v wget >/dev/null 2>&1; then
        wget -q --show-progress -O "$tmpzip" "$url"
    else
        echo "[scenes] ERROR: neither wget nor curl found" >&2
        return 1
    fi

    echo "[scenes] Extracting $name..."
    mkdir -p "$dest"
    unzip -q -o "$tmpzip" -d "$dest"
    rm -f "$tmpzip"

    # Flatten: if zip produced a single subdirectory, move contents up
    local entries=("$dest"/*)
    if [ ${#entries[@]} -eq 1 ] && [ -d "${entries[0]}" ]; then
        local subdir="${entries[0]}"
        echo "[scenes] Flattening ${subdir##*/}/ into $name/"
        mv "$subdir"/* "$dest/" 2>/dev/null || true
        mv "$subdir"/.* "$dest/" 2>/dev/null || true
        rmdir "$subdir" 2>/dev/null || true
    fi

    echo "[scenes] $name ready at $dest"
}

# ---------------------------------------------------------------------------
# 1. Arcade — bundled in release or Falcor media
# ---------------------------------------------------------------------------
if [ ! -d "$MEDIA_DIR/Arcade" ]; then
    if [ -d "$ROOT_DIR/runtime/media/Arcade" ]; then
        echo "[scenes] Copying Arcade from release bundle..."
        cp -r "$ROOT_DIR/runtime/media/Arcade" "$MEDIA_DIR/Arcade"
    elif [ -d "$ROOT_DIR/Falcor/media/Arcade" ]; then
        echo "[scenes] Copying Arcade from Falcor/media/..."
        cp -r "$ROOT_DIR/Falcor/media/Arcade" "$MEDIA_DIR/Arcade"
    else
        echo "[scenes] WARNING: Arcade not found. Run download_release first, or build Falcor to get Falcor/media/Arcade."
    fi
else
    echo "[scenes] Arcade already exists, skipping"
fi

# ---------------------------------------------------------------------------
# 2. Cornell Box — bundled in release or Falcor test_scenes
# ---------------------------------------------------------------------------
if [ ! -d "$MEDIA_DIR/TestScenes" ]; then
    if [ -d "$ROOT_DIR/runtime/media/TestScenes" ]; then
        echo "[scenes] Copying TestScenes from release bundle..."
        cp -r "$ROOT_DIR/runtime/media/TestScenes" "$MEDIA_DIR/TestScenes"
    elif [ -d "$ROOT_DIR/Falcor/media/TestScenes" ]; then
        echo "[scenes] Copying TestScenes from Falcor/media/..."
        cp -r "$ROOT_DIR/Falcor/media/TestScenes" "$MEDIA_DIR/TestScenes"
    else
        echo "[scenes] WARNING: TestScenes not found. Run download_release first, or build Falcor to get Falcor/media/TestScenes."
    fi
else
    echo "[scenes] TestScenes already exists, skipping"
fi
# Copy CornellBox pyscene from repo if missing
if [ -d "$MEDIA_DIR/TestScenes" ] && [ ! -f "$MEDIA_DIR/TestScenes/CornellBox_1AreaLight.pyscene" ] && [ -f "$SCENES_DIR/CornellBox_1AreaLight.pyscene" ]; then
    cp "$SCENES_DIR/CornellBox_1AreaLight.pyscene" "$MEDIA_DIR/TestScenes/CornellBox_1AreaLight.pyscene"
    echo "[scenes] Copied CornellBox_1AreaLight.pyscene from scenes/"
fi

# ---------------------------------------------------------------------------
# 3. Bistro (Amazon Lumberyard / NVIDIA ORCA)
#    Official NVIDIA ORCA download — CC-BY 4.0 license.
#    The URL redirects (302) to a tokenized download; curl -L handles it.
#    Previously: casual-effects.com/g3d/.../Bistro_v5_2.zip (dead as of 2025)
# ---------------------------------------------------------------------------
BISTRO_URL="https://developer.nvidia.com/downloads/bistro"

if [ ! -d "$MEDIA_DIR/Bistro" ]; then
    echo ""
    echo "[scenes] === Bistro (Amazon Lumberyard) ==="
    echo "[scenes] Source: developer.nvidia.com/orca (NVIDIA ORCA)"
    echo "[scenes] Size: ~3.2 GB compressed"
    echo ""
    read -rp "[scenes] Download Bistro? [y/N] " yn
    case "$yn" in
        [Yy]*)
            download_and_extract "Bistro" "$BISTRO_URL"
            # Copy pyscenes from repo if not already present (NVIDIA ORCA ships its own too)
            for pf in BistroInterior.pyscene BistroExterior.pyscene; do
                if [ ! -f "$MEDIA_DIR/Bistro/$pf" ] && [ -f "$SCENES_DIR/$pf" ]; then
                    cp "$SCENES_DIR/$pf" "$MEDIA_DIR/Bistro/$pf"
                    echo "[scenes] Copied $pf from scenes/"
                fi
            done
            ;;
        *) echo "[scenes] Skipping Bistro" ;;
    esac
else
    echo "[scenes] Bistro already exists, skipping"
fi

# ---------------------------------------------------------------------------
# 4. Sponza (Crytek)
#    GitHub mirror of the Crytek Sponza OBJ model (Frank Meinl).
#    Previously: casual-effects.com/g3d/.../CrytekSponza/sponza.zip (dead as of 2025)
# ---------------------------------------------------------------------------
SPONZA_URL="https://github.com/jimmiebergmann/Sponza/archive/refs/heads/master.zip"

if [ ! -d "$MEDIA_DIR/Sponza" ]; then
    echo ""
    echo "[scenes] === Sponza (Crytek) ==="
    echo "[scenes] Source: github.com/jimmiebergmann/Sponza (OBJ mirror)"
    echo "[scenes] Size: ~70 MB compressed"
    echo ""
    read -rp "[scenes] Download Sponza? [y/N] " yn
    case "$yn" in
        [Yy]*)
            download_and_extract "Sponza" "$SPONZA_URL"
            # Fix Crytek Sponza MTL: d 0.000000 (fully transparent) → d 1.000000 (opaque)
            # This is a known bug in the Crytek Sponza OBJ distribution.
            if [ -f "$MEDIA_DIR/Sponza/sponza.mtl" ]; then
                sed -i 's/^d 0\.000000$/d 1.000000/' "$MEDIA_DIR/Sponza/sponza.mtl"
                echo "[scenes] Fixed Sponza MTL opacity (d 0.0 → d 1.0)"
            fi
            # Copy pyscene from repo if not already present
            if [ ! -f "$MEDIA_DIR/Sponza/Sponza.pyscene" ] && [ -f "$SCENES_DIR/Sponza.pyscene" ]; then
                cp "$SCENES_DIR/Sponza.pyscene" "$MEDIA_DIR/Sponza/Sponza.pyscene"
                echo "[scenes] Copied Sponza.pyscene from scenes/"
            fi
            ;;
        *) echo "[scenes] Skipping Sponza" ;;
    esac
else
    echo "[scenes] Sponza already exists, skipping"
fi

# ---------------------------------------------------------------------------
# 5. Rungholt (McGuire Computer Graphics Archive)
#    Medieval town, ~6M triangles, ~260m world extent — scale test scene.
#    Morgan McGuire, Computer Graphics Archive, July 2017.
#    https://casual-effects.com/data/
# ---------------------------------------------------------------------------
RUNGHOLT_URL="https://casual-effects.com/g3d/data10/research/model/rungholt/rungholt.zip"

if [ ! -d "$MEDIA_DIR/Rungholt" ]; then
    echo ""
    echo "[scenes] === Rungholt (McGuire CG Archive) ==="
    echo "[scenes] Source: casual-effects.com/data (CC BY 3.0)"
    echo "[scenes] Size: ~300 MB compressed (~6M triangles, medieval town)"
    echo ""
    read -rp "[scenes] Download Rungholt? [y/N] " yn
    case "$yn" in
        [Yy]*)
            download_and_extract "Rungholt" "$RUNGHOLT_URL"
            # Copy pyscene from repo if not already present
            if [ ! -f "$MEDIA_DIR/Rungholt/Rungholt.pyscene" ] && [ -f "$SCENES_DIR/Rungholt.pyscene" ]; then
                cp "$SCENES_DIR/Rungholt.pyscene" "$MEDIA_DIR/Rungholt/Rungholt.pyscene"
                echo "[scenes] Copied Rungholt.pyscene from scenes/"
            fi
            ;;
        *) echo "[scenes] Skipping Rungholt" ;;
    esac
else
    echo "[scenes] Rungholt already exists, skipping"
fi

# ---------------------------------------------------------------------------
# 6. Sun Temple (Epic Games / NVIDIA ORCA)
#    Temple complex, ~600K triangles — FBX format.
#    Epic Games, Unreal Engine Sun Temple, NVIDIA ORCA, October 2017.
#    https://developer.nvidia.com/ue4-sun-temple
# ---------------------------------------------------------------------------
SUNTEMPLE_URL="https://developer.nvidia.com/ue4-sun-temple"

if [ ! -d "$MEDIA_DIR/SunTemple" ]; then
    echo ""
    echo "[scenes] === Sun Temple (Epic Games / NVIDIA ORCA) ==="
    echo "[scenes] Source: developer.nvidia.com/orca (NVIDIA ORCA)"
    echo "[scenes] Size: ~400 MB compressed (~600K triangles, temple complex)"
    echo ""
    read -rp "[scenes] Download Sun Temple? [y/N] " yn
    case "$yn" in
        [Yy]*)
            download_and_extract "SunTemple" "$SUNTEMPLE_URL"
            # Copy pyscene from repo if not already present
            if [ ! -f "$MEDIA_DIR/SunTemple/SunTemple.pyscene" ] && [ -f "$SCENES_DIR/SunTemple.pyscene" ]; then
                cp "$SCENES_DIR/SunTemple.pyscene" "$MEDIA_DIR/SunTemple/SunTemple.pyscene"
                echo "[scenes] Copied SunTemple.pyscene from scenes/"
            fi
            ;;
        *) echo "[scenes] Skipping Sun Temple" ;;
    esac
else
    echo "[scenes] SunTemple already exists, skipping"
fi

# ---------------------------------------------------------------------------
# 7. Manhattan (Sketchfab — manual download, CC-BY 4.0)
#    Entire Manhattan Island from OSM data, 2.9M triangles, ~21 km extent.
#    Requires free Sketchfab account to download.
#    https://sketchfab.com/3d-models/manhattan-osm-complete-model-bad7b7c7c6a64febb83950c24fee4d00
# ---------------------------------------------------------------------------
if [ ! -d "$MEDIA_DIR/Manhattan" ]; then
    echo ""
    echo "[scenes] === Manhattan (Sketchfab / OSM) ==="
    echo "[scenes] This scene requires manual download (free Sketchfab account):"
    echo ""
    echo "  1. Visit: https://sketchfab.com/3d-models/manhattan-osm-complete-model-bad7b7c7c6a64febb83950c24fee4d00"
    echo "  2. Click 'Download 3D Model' (glTF format)"
    echo "  3. Extract to: $MEDIA_DIR/Manhattan/"
    echo ""
    echo "[scenes] Credit: MENUDQ2, OpenStreetMap contributors (CC-BY 4.0)"
    echo "[scenes] Used in Landscape.pyscene (Manhattan + Bistro in Central Park)"
    echo ""
else
    echo "[scenes] Manhattan already exists, skipping"
fi

# ---------------------------------------------------------------------------
# 8. VeachAjar — Bitterli's rendering resources, converted to OBJ by DQLin
#    Original scene: https://benedikt-bitterli.me/resources/ (Tungsten/PLY)
#    DQLin converted to OBJ + added teapot variants and animated door for
#    the ReSTIR PT demo. We fetch from DQLin's repo (the only OBJ source).
# ---------------------------------------------------------------------------
VEACHAJAR_REPO="https://github.com/DQLin/ReSTIR_PT"
VEACHAJAR_SUBPATH="Source/RenderPasses/ReSTIRPTPass/Data/VeachAjar"
VEACHAJAR_DEST="$ROOT_DIR/Source/RenderPasses/ReSTIRPTPass/Data/VeachAjar"

if [ -d "$VEACHAJAR_DEST/models" ] && [ -d "$VEACHAJAR_DEST/textures" ]; then
    echo "[scenes] VeachAjar already exists, skipping"
else
    echo ""
    echo "[scenes] === VeachAjar (Bitterli scene, DQLin OBJ conversion) ==="
    echo "[scenes] Source: github.com/DQLin/ReSTIR_PT"
    echo "[scenes] Original: benedikt-bitterli.me/resources (veach-ajar)"
    echo "[scenes] Size: ~62 MB (OBJ models + textures)"
    echo "[scenes] Destination: Source/RenderPasses/ReSTIRPTPass/Data/VeachAjar/"
    echo ""
    read -rp "[scenes] Download VeachAjar? [y/N] " yn
    case "$yn" in
        [Yy]*)
            echo "[scenes] Cloning DQLin/ReSTIR_PT (sparse, models+textures only)..."
            echo ""
            VEACH_TMPDIR="$(mktemp -d /tmp/veach-ajar.XXXXXX)"

            git clone --depth 1 --filter=blob:none --sparse \
                "$VEACHAJAR_REPO" "$VEACH_TMPDIR/repo" 2>&1

            cd "$VEACH_TMPDIR/repo"
            git sparse-checkout set "$VEACHAJAR_SUBPATH/models" "$VEACHAJAR_SUBPATH/textures" 2>&1
            cd "$ROOT_DIR"

            # Copy models and textures to destination
            mkdir -p "$VEACHAJAR_DEST/models" "$VEACHAJAR_DEST/textures"

            if [ -d "$VEACH_TMPDIR/repo/$VEACHAJAR_SUBPATH/models" ]; then
                cp -r "$VEACH_TMPDIR/repo/$VEACHAJAR_SUBPATH/models/"* "$VEACHAJAR_DEST/models/"
            else
                echo "[scenes] ERROR: models/ not found in cloned repo" >&2
                rm -rf "$VEACH_TMPDIR"
                exit 1
            fi

            if [ -d "$VEACH_TMPDIR/repo/$VEACHAJAR_SUBPATH/textures" ]; then
                cp -r "$VEACH_TMPDIR/repo/$VEACHAJAR_SUBPATH/textures/"* "$VEACHAJAR_DEST/textures/"
            fi

            rm -rf "$VEACH_TMPDIR"
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
echo "  Mogwai.exe --scene \"$MEDIA_DIR/Bistro/BistroInterior.pyscene\""
