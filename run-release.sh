#!/usr/bin/env bash
# run-release.sh — Smoke test + launch Mogwai.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec bash "$SCRIPT_DIR/scripts/run_release.sh" "$@"
