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

mkdir -p "$RELEASE_DIR"

# ---------------------------------------------------------------------------
# Check for newer release via ETag
# ---------------------------------------------------------------------------
if [ -f "$RELEASE_DIR/Mogwai.exe" ] || [ -f "$RELEASE_DIR/Mogwai" ]; then
    if [ -f "$ETAG_FILE" ]; then
        OLD_ETAG="$(cat "$ETAG_FILE")"
        echo "[release] Checking for newer release..."
        REMOTE_ETAG="$(curl -fsSL -I "$DOWNLOAD_URL" 2>/dev/null | grep -i '^etag:' | awk '{print $2}' | tr -d '\r')" || true
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
    curl -fSL --progress-bar -D "$HEADERS" -o "$ARCHIVE" "$DOWNLOAD_URL" || {
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

echo "[release] Extracting to $RELEASE_DIR..."
tar xzf "$ARCHIVE" -C "$RELEASE_DIR"
rm -f "$ARCHIVE"
echo "[release] Release ready at $RELEASE_DIR"
