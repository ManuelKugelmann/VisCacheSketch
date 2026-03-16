#!/usr/bin/env bash
# download_release.sh — Download latest VisCacheSketch GitHub release (Mogwai + plugins).
#
# Usage:  ./scripts/download_release.sh
#
# Downloads the dev-latest prerelease archive and extracts to release/.
# Re-downloads if a newer release is available (uses ETag to check).
#
# Requires: curl or wget, tar

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RELEASE_DIR="${ROOT_DIR}/release"
REPO="ManuelKugelmann/VisCacheSketch"
DOWNLOAD_URL="https://github.com/${REPO}/releases/download/dev-latest/viscache-windows-Release.tar.gz"
ETAG_FILE="${RELEASE_DIR}/.release-etag"
VERSION_FILE="${RELEASE_DIR}/.release-version"
API_URL="https://api.github.com/repos/${REPO}/releases/tags/dev-latest"

mkdir -p "$RELEASE_DIR"

# ---------------------------------------------------------------------------
# Check for newer release via ETag
# ---------------------------------------------------------------------------
if [ -f "$RELEASE_DIR/Mogwai.exe" ] || [ -f "$RELEASE_DIR/Mogwai" ]; then
    if [ -f "$ETAG_FILE" ]; then
        OLD_ETAG="$(cat "$ETAG_FILE")"
        echo "[release] Checking for newer release..."
        REMOTE_ETAG="$(curl -fsSL -H 'Cache-Control: no-cache' -I "$DOWNLOAD_URL" 2>/dev/null | grep -i '^etag:' | awk '{print $2}' | tr -d '\r')" || true
        # Query GitHub API for tag+date display
        REMOTE_TAG=""
        REMOTE_DATE=""
        API_JSON="$(curl -fsSL "$API_URL" 2>/dev/null)" || true
        if [ -n "$API_JSON" ]; then
            REMOTE_TAG="$(echo "$API_JSON" | grep -o '"tag_name"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')" || true
            REMOTE_DATE="$(echo "$API_JSON" | grep -o '"published_at"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"\([0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}\).*/\1/')" || true
        fi
        # Show installed version with short ETag
        INSTALLED_VER="unknown"
        [ -f "$VERSION_FILE" ] && INSTALLED_VER="$(cat "$VERSION_FILE")"
        OLD_ETAG_SHORT="${OLD_ETAG:0:8}"
        echo "[release]   Installed: $INSTALLED_VER [etag:$OLD_ETAG_SHORT]"
        if [ -n "$REMOTE_TAG" ]; then
            if [ -n "$REMOTE_ETAG" ]; then
                REMOTE_ETAG_SHORT="${REMOTE_ETAG:0:8}"
                echo "[release]   Remote:    $REMOTE_TAG ($REMOTE_DATE) [etag:$REMOTE_ETAG_SHORT]"
            else
                echo "[release]   Remote:    $REMOTE_TAG ($REMOTE_DATE)"
            fi
        else
            echo "[release]   Remote:    (could not query GitHub API)"
        fi
        if [ -n "$REMOTE_ETAG" ] && [ "$REMOTE_ETAG" = "$OLD_ETAG" ]; then
            echo "[release] Release is up to date."
            exit 0
        elif [ -z "$REMOTE_ETAG" ]; then
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
HEADERS="$(mktemp /tmp/viscache-headers.XXXXXX.txt)"

if command -v curl >/dev/null 2>&1; then
    curl -fSL --progress-bar -H 'Cache-Control: no-cache' -D "$HEADERS" -o "$ARCHIVE" "$DOWNLOAD_URL" || {
        echo "[release] Download failed -- no dev-latest release yet. Skipping."
        echo "[release] This is normal for first-time setup or pre-release branches."
        rm -f "$ARCHIVE" "$HEADERS"
        exit 0
    }
elif command -v wget >/dev/null 2>&1; then
    wget -q --show-progress --save-headers -O "$ARCHIVE" "$DOWNLOAD_URL" 2>"$HEADERS" || {
        echo "[release] Download failed -- no dev-latest release yet. Skipping."
        rm -f "$ARCHIVE" "$HEADERS"
        exit 0
    }
else
    echo "[release] ERROR: neither curl nor wget found" >&2
    exit 1
fi

# Save ETag for future update checks
ETAG="$(grep -i '^etag:' "$HEADERS" 2>/dev/null | awk '{print $2}' | tr -d '\r')" || true
if [ -n "$ETAG" ]; then
    echo "$ETAG" > "$ETAG_FILE"
fi
rm -f "$HEADERS"

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
    # Preserve ETag and version files
    if [ -f "$OLD_RELEASE/release/.release-etag" ]; then
        cp "$OLD_RELEASE/release/.release-etag" "$ETAG_FILE"
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
