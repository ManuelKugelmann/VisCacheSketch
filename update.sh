#!/usr/bin/env bash
# update.sh — In-repo equivalent of the one-liner install command.
#
# Usage:  ./update.sh [--scene Bistro|Sponza|Arcade] [--skip-scenes]
#
# What it does (same as the curl one-liner, but from inside the repo):
#   1. git pull origin <current branch>
#   2. scripts/quickstart.sh (download scenes, download release, run tests, launch)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ---------------------------------------------------------------------------
# Step 1: Pull latest
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo " Step 1: Pull latest changes"
echo "========================================"

BRANCH="$(git -C "$SCRIPT_DIR" rev-parse --abbrev-ref HEAD)"
echo "[update] Branch: $BRANCH"
git -C "$SCRIPT_DIR" pull origin "$BRANCH" || echo "[update] WARNING: pull failed, continuing with current checkout"

# ---------------------------------------------------------------------------
# Step 2: Quickstart (scenes, release, tests, launch)
# ---------------------------------------------------------------------------
echo ""
echo "========================================"
echo " Step 2: Quickstart"
echo "========================================"
bash "$SCRIPT_DIR/scripts/quickstart.sh" "$@"
