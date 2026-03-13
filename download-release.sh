#!/usr/bin/env bash
# download-release.sh — Download latest GitHub release (Mogwai + plugins).
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec bash "$SCRIPT_DIR/scripts/download_release.sh" "$@"
