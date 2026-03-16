#!/usr/bin/env bash
# download_release.sh — Download latest VisCacheSketch GitHub release (Mogwai + plugins).
#
# Usage:  ./scripts/download_release.sh
#
# Downloads the dev-latest prerelease archive and extracts to release/.
# Re-downloads if a newer release is available (compares commit SHA via API).
#
# Requires: curl or wget, tar

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RELEASE_DIR="${ROOT_DIR}/release"
REPO="ManuelKugelmann/VisCacheSketch"
DOWNLOAD_URL="https://github.com/${REPO}/releases/download/dev-latest/viscache-windows-Release.tar.gz"
SHA_FILE="${RELEASE_DIR}/.release-sha"
VERSION_FILE="${RELEASE_DIR}/.release-version"
API_URL="https://api.github.com/repos/${REPO}/releases/tags/dev-latest"

mkdir -p "$RELEASE_DIR"

# ---------------------------------------------------------------------------
# Query remote release info from GitHub API (single call)
# ---------------------------------------------------------------------------
REMOTE_TAG=""
REMOTE_DATE=""
REMOTE_SHA=""
API_JSON="$(curl -fsSL "$API_URL" 2>/dev/null)" || true
if [ -n "$API_JSON" ]; then
    REMOTE_TAG="$(echo "$API_JSON" | grep -o '"tag_name"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')" || true
    REMOTE_DATE="$(echo "$API_JSON" | grep -o '"published_at"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}\).*/\1/')" || true
    REMOTE_SHA="$(echo "$API_JSON" | grep -o '"target_commitish"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"target_commitish"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')" || true
fi

# ---------------------------------------------------------------------------
# Check for newer release via commit SHA from GitHub API
# ---------------------------------------------------------------------------
if [ -f "$RELEASE_DIR/Mogwai.exe" ] || [ -f "$RELEASE_DIR/Mogwai" ]; then
    if [ -f "$SHA_FILE" ]; then
        OLD_SHA="$(cat "$SHA_FILE")"
        echo "[release] Checking for newer release..."
        INSTALLED_VER="unknown"
        [ -f "$VERSION_FILE" ] && INSTALLED_VER="$(cat "$VERSION_FILE")"
        OLD_SHA_SHORT="${OLD_SHA:0:7}"
        echo "[release]   Installed: $INSTALLED_VER [$OLD_SHA_SHORT]"
        if [ -n "$REMOTE_TAG" ]; then
            if [ -n "$REMOTE_SHA" ]; then
                REMOTE_SHA_SHORT="${REMOTE_SHA:0:7}"
                echo "[release]   Remote:    $REMOTE_TAG ($REMOTE_DATE) [$REMOTE_SHA_SHORT]"
            else
                echo "[release]   Remote:    $REMOTE_TAG ($REMOTE_DATE)"
            fi
        else
            echo "[release]   Remote:    (could not query GitHub API)"
        fi
        if [ -n "$REMOTE_SHA" ] && [ "$REMOTE_SHA" = "$OLD_SHA" ]; then
            echo "[release] Release is up to date."
            exit 0
        elif [ -z "$REMOTE_SHA" ]; then
            echo "[release] Could not check remote -- keeping existing release."
            exit 0
        fi
        echo "[release] Newer release available, updating..."
    else
        echo "[release] Release exists but no version info. Re-downloading..."
    fi
fi

# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------
echo "[release] Downloading: $DOWNLOAD_URL"
ARCHIVE="$(mktemp /tmp/viscache-release.XXXXXX.tar.gz)"

if command -v curl >/dev/null 2>&1; then
    curl -fSL --progress-bar -H 'Cache-Control: no-cache' -o "$ARCHIVE" "$DOWNLOAD_URL" || {
        echo "[release] Download failed -- no dev-latest release yet. Skipping."
        echo "[release] This is normal for first-time setup or pre-release branches."
        rm -f "$ARCHIVE"
        exit 0
    }
elif command -v wget >/dev/null 2>&1; then
    wget -q --show-progress -O "$ARCHIVE" "$DOWNLOAD_URL" || {
        echo "[release] Download failed -- no dev-latest release yet. Skipping."
        rm -f "$ARCHIVE"
        exit 0
    }
else
    echo "[release] ERROR: neither curl nor wget found" >&2
    exit 1
fi

# Save commit SHA for future update checks
if [ -n "${REMOTE_SHA:-}" ]; then
    echo "$REMOTE_SHA" > "$SHA_FILE"
fi

# Save release version for display on next update check
if [ -n "${REMOTE_TAG:-}" ]; then
    echo "$REMOTE_TAG ($REMOTE_DATE)" > "$VERSION_FILE"
else
    echo "dev-latest" > "$VERSION_FILE"
fi

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
    rm -f "$ARCHIVE"
    exit 1
fi
rm -f "$ARCHIVE"

# Remove old release now that extraction succeeded
rm -rf "$OLD_RELEASE"
echo "[release] Release ready at $RELEASE_DIR"
