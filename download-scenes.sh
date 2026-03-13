#!/usr/bin/env bash
# download-scenes.sh — Fetch test scenes.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec bash "$SCRIPT_DIR/scripts/download_scenes.sh" "$@"
