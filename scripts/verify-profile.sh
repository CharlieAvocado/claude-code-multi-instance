#!/bin/sh
# Check that a Claude Code profile is whole.
# Usage: sh verify-profile.sh [config-dir]     (default: $CLAUDE_CONFIG_DIR or ~/.claude)
D="${1:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}}"
echo "profile: $D"
for p in projects jobs file-history session-env plugins; do
    if [ -d "$D/$p" ]; then echo "  ok    $p/ ($(ls -1 "$D/$p" | wc -l | tr -d ' ') entries)"
    else echo "  MISS  $p/"; fi
done
for f in history.jsonl settings.json .claude.json .credentials.json; do
    path="$D/$f"
    # The default profile keeps .claude.json in the home folder, not in ~/.claude.
    [ "$f" = .claude.json ] && [ "$D" = "$HOME/.claude" ] && path="$HOME/.claude.json"
    if [ -f "$path" ]; then echo "  ok    $f"; else echo "  MISS  $f"; fi
done
[ -n "$CLAUDE_CODE_PLUGIN_CACHE_DIR" ] && echo "  note  plugins come from shared store $CLAUDE_CODE_PLUGIN_CACHE_DIR"
if [ -f "$D/settings.json" ]; then
    python3 - "$D/settings.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
p = s.get("permissions", {})
print(f"  settings: {len(p.get('deny', []))} deny, {len(p.get('ask', []))} ask, "
      f"{len(p.get('allow', []))} allow, hooks: {sorted(s.get('hooks', {})) or 'none'}")
print(f"  cleanupPeriodDays: {s.get('cleanupPeriodDays', 'UNSET (default pruning applies)')}")
print(f"  enabledPlugins: {sorted(k for k, v in s.get('enabledPlugins', {}).items() if v) or 'none'}")
PY
fi
echo "macOS keeps the login in the Keychain, so a missing .credentials.json there is normal."
