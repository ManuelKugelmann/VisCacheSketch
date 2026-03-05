#!/bin/bash
# sync-submodules.sh — Keep root .gitmodules and Falcor/.gitmodules in sync
#
# Falcor is a git subtree. Git only reads the ROOT .gitmodules for submodule
# config, but upstream Falcor expects its own .gitmodules to be authoritative.
# This script syncs between the two.
#
# Usage:
#   ./sync-submodules.sh from-upstream   # after: git subtree pull --prefix=Falcor ...
#   ./sync-submodules.sh to-upstream     # before: git subtree push --prefix=Falcor ...
#   ./sync-submodules.sh check           # just check, no changes (same as pre-commit hook)
#
# from-upstream: Falcor/.gitmodules is authoritative → regenerate root .gitmodules
# to-upstream:   root .gitmodules is authoritative → regenerate Falcor/.gitmodules

set -euo pipefail

FALCOR_GITMODULES="Falcor/.gitmodules"
ROOT_GITMODULES=".gitmodules"

log()  { echo -e "\033[36m[sync]\033[0m $1"; }
fail() { echo -e "\033[31m[sync] ERROR:\033[0m $1"; exit 1; }

# Parse .gitmodules into path<TAB>url lines
# Usage: parse_gitmodules <file> <prefix_to_strip>
parse_gitmodules() {
    local file="$1" strip="$2"
    local current_path="" current_url=""
    while IFS= read -r line; do
        case "$line" in
            *"path = "*) current_path="${line#*path = }"; [ -n "$strip" ] && current_path="${current_path#"$strip"}" ;;
            *"url = "*)  current_url="${line#*url = }" ;;
        esac
        if [ -n "$current_path" ] && [ -n "$current_url" ]; then
            printf '%s\t%s\n' "$current_path" "$current_url"
            current_path="" current_url=""
        fi
    done < "$file"
}

# Generate a .gitmodules file from path<TAB>url lines
# Usage: generate_gitmodules <prefix> < path_url_lines
# prefix is prepended to both the submodule name and path
generate_gitmodules() {
    local prefix="$1"
    while IFS=$'\t' read -r path url; do
        echo "[submodule \"${prefix}${path}\"]"
        echo "	path = ${prefix}${path}"
        echo "	url = ${url}"
    done
}

check_sync() {
    [ -f "$FALCOR_GITMODULES" ] || { log "No $FALCOR_GITMODULES, nothing to check"; return 0; }
    [ -f "$ROOT_GITMODULES" ] || fail "$ROOT_GITMODULES missing"

    local falcor_map root_map
    falcor_map=$(mktemp)
    root_map=$(mktemp)
    trap 'rm -f "$falcor_map" "$root_map"' RETURN

    parse_gitmodules "$FALCOR_GITMODULES" "" > "$falcor_map"
    parse_gitmodules "$ROOT_GITMODULES" "Falcor/" > "$root_map"

    local errors=0

    # Falcor → root
    while IFS=$'\t' read -r path url; do
        local root_url
        root_url=$(grep "^${path}"$'\t' "$root_map" | cut -f2) || true
        if [ -z "$root_url" ]; then
            echo "  MISSING in root .gitmodules: '${path}' (expected as 'Falcor/${path}')"
            errors=$((errors + 1))
        elif [ "$url" != "$root_url" ]; then
            echo "  URL MISMATCH: '${path}'"
            echo "    Falcor/.gitmodules: $url"
            echo "    .gitmodules:        $root_url"
            errors=$((errors + 1))
        fi
    done < "$falcor_map"

    # root → Falcor
    while IFS=$'\t' read -r path url; do
        local falcor_url
        falcor_url=$(grep "^${path}"$'\t' "$falcor_map" | cut -f2) || true
        if [ -z "$falcor_url" ]; then
            echo "  STALE in root .gitmodules: 'Falcor/${path}' not in Falcor/.gitmodules"
            errors=$((errors + 1))
        fi
    done < "$root_map"

    return $errors
}

from_upstream() {
    [ -f "$FALCOR_GITMODULES" ] || fail "$FALCOR_GITMODULES not found"
    log "Syncing: Falcor/.gitmodules → root .gitmodules"

    local falcor_map
    falcor_map=$(mktemp)
    trap 'rm -f "$falcor_map"' RETURN
    parse_gitmodules "$FALCOR_GITMODULES" "" > "$falcor_map"

    local count
    count=$(wc -l < "$falcor_map")
    log "Found $count submodules in Falcor/.gitmodules"

    # Generate new root .gitmodules with Falcor/ prefix
    generate_gitmodules "Falcor/" < "$falcor_map" > "$ROOT_GITMODULES"
    log "Wrote $ROOT_GITMODULES ($count entries)"

    # Tell git to re-read .gitmodules
    git submodule sync 2>/dev/null || true
    log "Done. Review changes with: git diff .gitmodules"
}

to_upstream() {
    [ -f "$ROOT_GITMODULES" ] || fail "$ROOT_GITMODULES not found"
    log "Syncing: root .gitmodules → Falcor/.gitmodules"

    local root_map
    root_map=$(mktemp)
    trap 'rm -f "$root_map"' RETURN
    parse_gitmodules "$ROOT_GITMODULES" "Falcor/" > "$root_map"

    local count
    count=$(wc -l < "$root_map")
    if [ "$count" -eq 0 ]; then
        fail "No Falcor/ submodules found in $ROOT_GITMODULES"
    fi
    log "Found $count Falcor submodules in root .gitmodules"

    # Generate Falcor/.gitmodules without prefix (Falcor-relative paths)
    generate_gitmodules "" < "$root_map" > "$FALCOR_GITMODULES"
    log "Wrote $FALCOR_GITMODULES ($count entries)"
    log "Done. Review changes with: git diff Falcor/.gitmodules"
}

# ---------------------------------------------------------------------------
case "${1:-}" in
    from-upstream)
        from_upstream
        ;;
    to-upstream)
        to_upstream
        ;;
    check)
        log "Checking .gitmodules sync..."
        if check_sync; then
            log "In sync."
        else
            echo ""
            log "Out of sync. Run one of:"
            log "  ./sync-submodules.sh from-upstream   # after subtree pull"
            log "  ./sync-submodules.sh to-upstream     # before subtree push"
            exit 1
        fi
        ;;
    *)
        echo "Usage: $0 {from-upstream|to-upstream|check}"
        echo ""
        echo "  from-upstream  Falcor/.gitmodules → root .gitmodules  (after subtree pull)"
        echo "  to-upstream    root .gitmodules → Falcor/.gitmodules  (before subtree push)"
        echo "  check          verify both are in sync (no changes)"
        exit 1
        ;;
esac
