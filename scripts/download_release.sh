#!/usr/bin/env bash
# download_release.sh — Download latest VisCacheSketch GitHub release (Mogwai + plugins).
#
# Usage:  ./scripts/download_release.sh
#
# Finds the newest dev-* versioned prerelease via the GitHub API,
# downloads its archive, and extracts to release/.
# Re-downloads if a newer release is available (compares commit SHA).
#
# Requires: curl or wget, tar

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RELEASE_DIR="${ROOT_DIR}/release"
REPO="ManuelKugelmann/VisCacheSketch"
SHA_FILE="${RELEASE_DIR}/.release-sha"
VERSION_FILE="${RELEASE_DIR}/.release-version"

mkdir -p "$RELEASE_DIR"

# ---------------------------------------------------------------------------
# Step 1: Find the latest dev-* prerelease tag via GitHub API
# ---------------------------------------------------------------------------
REMOTE_TAG=""
API_LIST="$(curl -fsSL -H 'Cache-Control: no-cache' -H 'Pragma: no-cache' \
    "https://api.github.com/repos/${REPO}/releases?per_page=10" 2>/dev/null)" || true

if [ -n "$API_LIST" ]; then
    # Find first tag matching dev-2* (versioned tags, newest first)
    REMOTE_TAG="$(echo "$API_LIST" | grep -o '"tag_name"[[:space:]]*:[[:space:]]*"dev-2[^"]*"' | head -1 | sed 's/.*"\(dev-2[^"]*\)".*/\1/')" || true
fi

if [ -z "$REMOTE_TAG" ]; then
    echo "[release] No dev-* prerelease found on GitHub."
    if [ -f "$RELEASE_DIR/Mogwai.exe" ] || [ -f "$RELEASE_DIR/Mogwai" ]; then
        echo "[release] Keeping existing release."
        exit 0
    else
        echo "[release] No existing release and could not query remote."
        echo "[release] To get Mogwai manually:"
        echo "[release]   Download: https://github.com/${REPO}/releases"
        echo "[release]   Build:    run setup-build-system.bat, then cmake --preset windows-vs2022-ci"
        exit 0
    fi
fi

echo "[release] Latest prerelease tag: $REMOTE_TAG"

# ---------------------------------------------------------------------------
# Step 2: Fetch details for that specific release
# ---------------------------------------------------------------------------
REMOTE_DATE=""
REMOTE_SHA=""
API_JSON="$(curl -fsSL -H 'Cache-Control: no-cache' -H 'Pragma: no-cache' \
    "https://api.github.com/repos/${REPO}/releases/tags/${REMOTE_TAG}" 2>/dev/null)" || true

if [ -n "$API_JSON" ]; then
    # Extract full datetime (YYYY-MM-DD HH:MM:SS) from published_at
    REMOTE_DATE="$(echo "$API_JSON" | grep -o '"published_at"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 \
        | sed 's/.*"\([0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}\)T\([0-9:]*\).*/\1 \2/')" || true
    REMOTE_SHA="$(echo "$API_JSON" | grep -o '"target_commitish"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 \
        | sed 's/.*"target_commitish"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')" || true
fi

# ---------------------------------------------------------------------------
# Check for newer release via commit SHA
# ---------------------------------------------------------------------------
if [ -f "$RELEASE_DIR/Mogwai.exe" ] || [ -f "$RELEASE_DIR/Mogwai" ]; then
    if [ -f "$SHA_FILE" ]; then
        OLD_SHA="$(cat "$SHA_FILE")"
        echo "[release] Checking for newer release..."
        INSTALLED_VER="unknown"
        [ -f "$VERSION_FILE" ] && INSTALLED_VER="$(cat "$VERSION_FILE")"
        OLD_SHA_SHORT="${OLD_SHA:0:7}"
        echo "[release]   Installed: $INSTALLED_VER [$OLD_SHA_SHORT]"
        if [ -n "$REMOTE_SHA" ]; then
            REMOTE_SHA_SHORT="${REMOTE_SHA:0:7}"
            echo "[release]   Remote:    $REMOTE_TAG ($REMOTE_DATE) [$REMOTE_SHA_SHORT]"
        else
            echo "[release]   Remote:    $REMOTE_TAG ($REMOTE_DATE)"
        fi
        if [ -n "$REMOTE_SHA" ] && [ "$REMOTE_SHA" = "$OLD_SHA" ]; then
            echo "[release] Release is up to date."
            exit 0
        elif [ -z "$REMOTE_SHA" ]; then
            echo "[release] Could not verify remote SHA -- keeping existing release."
            exit 0
        fi
        echo "[release] Newer release available, updating..."
    else
        echo "[release] Release exists but no version info. Re-downloading..."
    fi
fi

# ---------------------------------------------------------------------------
# Download from the versioned tag (fall back to dev-latest if asset missing)
# ---------------------------------------------------------------------------
ASSET_NAME="viscache-windows-Release.tar.gz"
DOWNLOAD_URL="https://github.com/${REPO}/releases/download/${REMOTE_TAG}/${ASSET_NAME}"
echo "[release] Downloading: $DOWNLOAD_URL"
ARCHIVE="$(mktemp /tmp/viscache-release.XXXXXX.tar.gz)"

DOWNLOAD_OK=0
if command -v curl >/dev/null 2>&1; then
    curl -fSL --progress-bar -H 'Cache-Control: no-cache' -o "$ARCHIVE" "$DOWNLOAD_URL" 2>/dev/null && DOWNLOAD_OK=1
    if [ "$DOWNLOAD_OK" -eq 0 ]; then
        echo "[release] Asset not found on versioned tag, trying dev-latest..."
        FALLBACK_URL="https://github.com/${REPO}/releases/download/dev-latest/${ASSET_NAME}"
        curl -fSL --progress-bar -H 'Cache-Control: no-cache' -o "$ARCHIVE" "$FALLBACK_URL" && DOWNLOAD_OK=1
    fi
elif command -v wget >/dev/null 2>&1; then
    wget -q --show-progress -O "$ARCHIVE" "$DOWNLOAD_URL" 2>/dev/null && DOWNLOAD_OK=1
    if [ "$DOWNLOAD_OK" -eq 0 ]; then
        echo "[release] Asset not found on versioned tag, trying dev-latest..."
        FALLBACK_URL="https://github.com/${REPO}/releases/download/dev-latest/${ASSET_NAME}"
        wget -q --show-progress -O "$ARCHIVE" "$FALLBACK_URL" && DOWNLOAD_OK=1
    fi
else
    echo "[release] ERROR: neither curl nor wget found" >&2
    exit 1
fi

if [ "$DOWNLOAD_OK" -eq 0 ]; then
    echo "[release] Download failed. Skipping."
    echo "[release] This is normal for first-time setup or pre-release branches."
    rm -f "$ARCHIVE"
    exit 0
fi

# Save commit SHA for future update checks
if [ -n "${REMOTE_SHA:-}" ]; then
    echo "$REMOTE_SHA" > "$SHA_FILE"
fi

# Save release version for display on next update check
echo "$REMOTE_TAG ($REMOTE_DATE)" > "$VERSION_FILE"

# ---------------------------------------------------------------------------
# Preserve local data (downloaded scenes, deployed data) across updates
# ---------------------------------------------------------------------------
LOCAL_DATA_BACKUP="$(mktemp -d /tmp/viscache-local-data.XXXXXX)"
LOCAL_DIRS_PRESERVED=()
for LOCAL_DIR in media data; do
    if [ -d "$RELEASE_DIR/$LOCAL_DIR" ]; then
        echo "[release] Preserving local $LOCAL_DIR/..."
        mv "$RELEASE_DIR/$LOCAL_DIR" "$LOCAL_DATA_BACKUP/$LOCAL_DIR"
        LOCAL_DIRS_PRESERVED+=("$LOCAL_DIR")
    fi
done

# ---------------------------------------------------------------------------
# Clean old release — move aside so tar doesn't hit overwrite errors
# ---------------------------------------------------------------------------
OLD_RELEASE="$(mktemp -d /tmp/viscache-old-release.XXXXXX)"
if [ -f "$RELEASE_DIR/Mogwai.exe" ] || [ -f "$RELEASE_DIR/Mogwai" ]; then
    echo "[release] Moving old release aside..."
    mv "$RELEASE_DIR" "$OLD_RELEASE/release"
    mkdir -p "$RELEASE_DIR"
    # Preserve SHA and version files
    if [ -f "$OLD_RELEASE/release/.release-sha" ]; then
        cp "$OLD_RELEASE/release/.release-sha" "$SHA_FILE"
    fi
    if [ -f "$OLD_RELEASE/release/.release-version" ]; then
        cp "$OLD_RELEASE/release/.release-version" "$VERSION_FILE"
    fi
fi

echo "[release] Extracting to $RELEASE_DIR..."
if ! tar xzf "$ARCHIVE" -C "$RELEASE_DIR"; then
    echo "[release] ERROR: Extraction failed."
    if [ -d "$OLD_RELEASE/release" ]; then
        echo "[release] Restoring previous release..."
        rm -rf "$RELEASE_DIR"
        mv "$OLD_RELEASE/release" "$RELEASE_DIR"
    fi
    # Restore local data on failure
    for LOCAL_DIR in "${LOCAL_DIRS_PRESERVED[@]}"; do
        if [ -d "$LOCAL_DATA_BACKUP/$LOCAL_DIR" ]; then
            mv "$LOCAL_DATA_BACKUP/$LOCAL_DIR" "$RELEASE_DIR/$LOCAL_DIR"
        fi
    done
    rm -rf "$LOCAL_DATA_BACKUP"
    rm -f "$ARCHIVE"
    exit 1
fi
rm -f "$ARCHIVE"

# ---------------------------------------------------------------------------
# Merge preserved local data back (keep new release files, add back local-only)
# ---------------------------------------------------------------------------
for LOCAL_DIR in "${LOCAL_DIRS_PRESERVED[@]}"; do
    if [ -d "$LOCAL_DATA_BACKUP/$LOCAL_DIR" ]; then
        mkdir -p "$RELEASE_DIR/$LOCAL_DIR"
        # Copy back items that don't exist in the new release (no overwrite)
        for item in "$LOCAL_DATA_BACKUP/$LOCAL_DIR"/*; do
            [ -e "$item" ] || continue
            basename_item="$(basename "$item")"
            if [ ! -e "$RELEASE_DIR/$LOCAL_DIR/$basename_item" ]; then
                echo "[release] Restoring local $LOCAL_DIR/$basename_item"
                mv "$item" "$RELEASE_DIR/$LOCAL_DIR/$basename_item"
            fi
        done
    fi
done
rm -rf "$LOCAL_DATA_BACKUP"

# Remove old release now that extraction succeeded
rm -rf "$OLD_RELEASE"
echo "[release] Release ready at $RELEASE_DIR"
