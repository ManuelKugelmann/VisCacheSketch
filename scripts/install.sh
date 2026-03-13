#!/usr/bin/env bash
# install.sh — Idempotent VisCacheSketch installer (clone + quickstart).
#
# One-liner (paste into terminal):
#   curl -sL "https://raw.githubusercontent.com/ManuelKugelmann/VisCacheSketch/main/scripts/install.sh?$(date +%s)" | bash
#
# What it does:
#   1. Checks git version (2.43+ recommended)
#   2. Clones the repo (or pulls if it already exists)
#   3. Runs scripts/quickstart.sh (scenes, release, tests)
#
# Safe to re-run: skips clone if the directory exists, pulls latest instead.
#
# Options:
#   install.sh [--dir <name>] [--branch <branch>] [--scene <scene>] [--skip-scenes]

set -euo pipefail

DIR="VisCacheSketch"
BRANCH="main"
SCENE=""
SKIP_SCENES=""
REPO_URL="https://github.com/ManuelKugelmann/VisCacheSketch.git"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dir) DIR="$2"; shift 2 ;;
        --branch) BRANCH="$2"; shift 2 ;;
        --scene) SCENE="$2"; shift 2 ;;
        --skip-scenes) SKIP_SCENES="--skip-scenes"; shift ;;
        *) echo "Usage: $0 [--dir <name>] [--branch <branch>] [--scene <scene>] [--skip-scenes]"; exit 1 ;;
    esac
done

# Check git
if ! command -v git >/dev/null 2>&1; then
    echo "[install] ERROR: git not found. Install git 2.43+ from https://git-scm.com"
    exit 1
fi

GIT_VER="$(git --version | awk '{print $3}')"
echo "[install] git $GIT_VER"

GIT_MAJOR="${GIT_VER%%.*}"
GIT_MINOR_TMP="${GIT_VER#*.}"
GIT_MINOR="${GIT_MINOR_TMP%%.*}"
if [[ "$GIT_MAJOR" -lt 2 ]] || { [[ "$GIT_MAJOR" -eq 2 ]] && [[ "$GIT_MINOR" -lt 43 ]]; }; then
    echo "[install] WARNING: git $GIT_VER detected. git 2.43+ recommended (sparse-checkout, filter)."
fi

# Clone or pull
if [ -d "$DIR/.git" ]; then
    echo "[install] $DIR already exists -- pulling latest..."
    cd "$DIR"
    git fetch origin "$BRANCH"
    git checkout "$BRANCH" 2>/dev/null || true
    git pull origin "$BRANCH" || echo "[install] WARNING: pull failed, continuing with existing checkout"
    cd ..
elif [ -d "$DIR" ]; then
    echo "[install] ERROR: $DIR exists but is not a git repo."
    echo "[install] Remove it or use --dir <other-name>."
    exit 1
else
    echo "[install] Cloning $REPO_URL..."
    git clone --branch "$BRANCH" "$REPO_URL" "$DIR"
fi

# Run quickstart
QS_ARGS=""
[ -n "$SCENE" ] && QS_ARGS="--scene $SCENE"
[ -n "$SKIP_SCENES" ] && QS_ARGS="$QS_ARGS $SKIP_SCENES"

echo "[install] Running $DIR/scripts/quickstart.sh $QS_ARGS"
cd "$DIR"
# shellcheck disable=SC2086
bash scripts/quickstart.sh $QS_ARGS
