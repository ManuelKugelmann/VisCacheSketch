#!/usr/bin/env bash
# version.sh — Print git SHA + timestamp for version tracking.
#
# Usage: source scripts/version.sh [prefix]
#   Prints: [prefix] version: <short-sha> (<date> <time>)
#   Sets:   VCS_SHA, VCS_TIMESTAMP
#
# Example output:
#   [install] version: 2f115e6 (2026-03-13 14:05:02)

_VCS_PREFIX="${1:-version}"

# --- Git SHA ---
if command -v git >/dev/null 2>&1 && git rev-parse --short HEAD >/dev/null 2>&1; then
    VCS_SHA="$(git rev-parse --short HEAD)"
else
    VCS_SHA="unknown"
fi

# --- Timestamp ---
VCS_TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo 'unknown')"

echo "[${_VCS_PREFIX}] version: ${VCS_SHA} (${VCS_TIMESTAMP})"

export VCS_SHA VCS_TIMESTAMP
