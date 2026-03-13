#!/usr/bin/env bash
# download_release.sh — Download latest VisCacheSketch GitHub release (Mogwai + plugins).
#
# Usage:  ./scripts/download_release.sh
#
# Downloads the dev-latest prerelease archive and extracts to release/.
# Idempotent: skips if release/ already contains binaries. Delete release/ to re-download.
#
# Requires: curl or wget, tar

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RELEASE_DIR="${ROOT_DIR}/release"
REPO="ManuelKugelmann/VisCacheSketch"

if [ -d "$RELEASE_DIR" ] && [ "$(ls -A "$RELEASE_DIR" 2>/dev/null)" ]; then
    echo "[release] Release directory already exists at $RELEASE_DIR"
    echo "[release] Delete $RELEASE_DIR to re-download."
    exit 0
fi

DOWNLOAD_URL="https://github.com/${REPO}/releases/download/dev-latest/viscache-windows-Release.tar.gz"
echo "[release] Downloading: $DOWNLOAD_URL"
mkdir -p "$RELEASE_DIR"

ARCHIVE="$(mktemp /tmp/viscache-release.XXXXXX.tar.gz)"

if command -v curl >/dev/null 2>&1; then
    curl -fSL --progress-bar -o "$ARCHIVE" "$DOWNLOAD_URL" || {
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

echo "[release] Extracting to $RELEASE_DIR..."
tar xzf "$ARCHIVE" -C "$RELEASE_DIR"
rm -f "$ARCHIVE"
echo "[release] Release ready at $RELEASE_DIR"
