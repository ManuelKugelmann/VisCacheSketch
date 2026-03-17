#!/usr/bin/env bash
# quickstart.sh — Convenience wrapper at repo root.
#
# Usage:  ./quickstart.sh [--scene VeachAjar|Bistro|Sponza|Arcade|CornellBox]
#                         [--renderer viscache|minimal] [--skip-scenes]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec bash "$SCRIPT_DIR/scripts/quickstart.sh" "$@"
