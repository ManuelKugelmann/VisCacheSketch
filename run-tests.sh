#!/usr/bin/env bash
# run-tests.sh — Run CPU algorithm tests.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec bash "$SCRIPT_DIR/scripts/run-tests.sh" "$@"
