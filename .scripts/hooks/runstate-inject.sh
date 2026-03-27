#!/usr/bin/env bash
# runstate-inject.sh — Inject .run-state into model context if changed since last seen.
#
# SessionStart: always inject (bootstraps new session with current state).
# UserPromptSubmit: inject only if changed since this session last saw it.
# Per-session tracking: runtime/.runstate/<session_id>.hash
#
# Stdin: Claude Code hook JSON { "session_id": "...", "hook_event_name": "..." }
# Stdout: JSON with additionalContext, or empty (silent)

STATE=".run-state"
[ -f "$STATE" ] || exit 0

PYTHON="python"
command -v python3 &>/dev/null && PYTHON="python3"

INPUT=$(cat)

# Parse session_id and event from stdin JSON using Python
read -r SESSION EVENT < <("$PYTHON" -c "
import json, sys
d = json.loads(sys.stdin.read())
print(d.get('session_id', 'unknown'), d.get('hook_event_name', '').strip())
" <<< "$INPUT" | tr -d '\r')

HASH_DIR="runtime/.runstate"
mkdir -p "$HASH_DIR"
HASH_FILE="$HASH_DIR/${SESSION}.hash"

CUR=$(md5sum "$STATE" 2>/dev/null | cut -d' ' -f1)
LST=$(cat "$HASH_FILE" 2>/dev/null || echo "")

# SessionStart: always inject; UserPromptSubmit: only if changed
if [ "$EVENT" != "SessionStart" ] && [ "$CUR" = "$LST" ]; then
    exit 0
fi

echo "$CUR" > "$HASH_FILE"

"$PYTHON" -c "
import json, sys
content = open('.run-state').read().rstrip()
event = sys.argv[1]
print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': event,
        'additionalContext': '[.run-state]\n' + content
    }
}))
" "$EVENT"
