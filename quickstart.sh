#!/usr/bin/env bash
# quickstart.sh — Convenience wrapper at repo root.
#
# Usage:  ./quickstart.sh [--scene Bistro|Sponza|Arcade] [--skip-scenes]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec bash "$SCRIPT_DIR/scripts/quickstart.sh" "$@"
