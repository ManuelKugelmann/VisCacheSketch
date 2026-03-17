#!/usr/bin/env bash
# init-refs.sh — Initialize reference submodules in refs/
#
# Usage:  ./scripts/init-refs.sh
#
# These are read-only reference repos used for diffing during the port.
# They are NOT build dependencies — the project builds without them.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

log() { echo -e "\033[36m[init-refs]\033[0m $1"; }

# Init + update only refs/ submodules (skip Falcor/external/ which are handled by packman/cmake)
for sm in refs/*; do
    [ -d "$sm" ] || continue
    name="$(basename "$sm")"
    if [ -f "$sm/.git" ] || [ -d "$sm/.git" ]; then
        log "$name: already initialized"
    else
        log "$name: initializing..."
        git submodule update --init --depth 1 "$sm"
        log "$name: done"
    fi
done

log "All reference submodules ready."
