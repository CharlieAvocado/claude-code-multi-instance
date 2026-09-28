#!/bin/sh
# Installs claude-git-guard system-wide, root-owned, so Claude can't change it.
# Run:  sudo sh git-guard/install.sh
# Works on Linux and macOS. Safe to re-run (updates).
set -eu
[ "$(id -u)" = 0 ] || { echo "Run with sudo."; exit 1; }
SRC="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="${SUDO_USER:?run via sudo from your own account}"
case "$(uname)" in
  Darwin) DEST="/Library/Application Support/ClaudeCode"; GROUP=wheel ;;
  *)      DEST="/etc/claude-code"; GROUP=root ;;
esac
PY=/usr/bin/python3
HOOKS="$DEST/git-hooks"

echo "== testing the guard before installing"
sudo -H -u "$USER_NAME" "$PY" "$SRC/test_guard.py" --live

echo "== installing to $DEST"
install -d -o root -g "$GROUP" -m 755 "$DEST" "$HOOKS"
install -o root -g "$GROUP" -m 644 "$SRC/git_guard.py" "$DEST/git_guard.py"
install -o root -g "$GROUP" -m 755 "$SRC/git-hooks/pre-push" "$HOOKS/pre-push"
install -o root -g "$GROUP" -m 755 "$SRC/git-hooks/chain" "$HOOKS/chain"
for h in applypatch-msg pre-applypatch post-applypatch pre-commit pre-merge-commit \
         prepare-commit-msg commit-msg post-commit pre-rebase post-checkout post-merge \
         post-rewrite pre-auto-gc push-to-checkout sendemail-validate \
         pre-receive update proc-receive post-receive post-update; do
  ln -sfn chain "$HOOKS/$h"
done

"$PY" - "$DEST" "$PY" <<'PYEOF'
import json, sys
dest, py = sys.argv[1], sys.argv[2]
gh_ask = ["gh repo create*", "gh repo edit*", "gh repo fork*", "gh repo sync*",
          "gh pr create*", "gh pr merge*", "gh release*", "gh gist*",
          "gh api*-X *", "gh api*--method*", "gh api*-f *", "gh api*-F *",
          "gh api*--field*", "gh api*--raw-field*", "gh api*--input*",
          "gh secret*", "gh variable*", "gh auth login*", "gh auth refresh*",
          "gh workflow*", "gh ssh-key*", "gh gpg-key*"]
deny = ["git push --force*", "git push -f*", "git push*--force-with-lease*",
        "git push*--mirror*", "git -C * push --force*", "git -C * push -f*",
        "git -C * push*--mirror*", "git clean*", "git -C * clean*",
        "git reflog expire*", "git update-ref*", "git filter-branch*",
        "git gc --prune*", "gh repo delete*", "gh repo edit*visibility*public*",
        "gh api*-X DELETE*repos/*"]
settings = {
    "disableAllHooks": False,
    "hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{
        "type": "command",
        "command": f'{py} "{dest}/git_guard.py" hook',
        "timeout": 60}]}]},
    "permissions": {
        "disableBypassPermissionsMode": "disable",
        "ask": [f"Bash({r})" for r in gh_ask],
        "deny": [f"Bash({r})" for r in deny] + [
            "Edit(~/.gitconfig)", "Edit(~/.config/git/**)", "Edit(**/.git/config)",
            "Edit(//etc/gitconfig)", "Edit(//etc/claude-code/**)",
            "Edit(//Library/Application Support/ClaudeCode/**)"],
    },
}
with open(f"{dest}/managed-settings.json", "w") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
PYEOF
chown root:"$GROUP" "$DEST/managed-settings.json"; chmod 644 "$DEST/managed-settings.json"
git config --system core.hooksPath "$HOOKS"

echo "== self-test of the installed copy"
T="$(sudo -H -u "$USER_NAME" mktemp -d)"
sudo -H -u "$USER_NAME" git init -q "$T/pub"
sudo -H -u "$USER_NAME" git -C "$T/pub" remote add origin https://github.com/octocat/Hello-World.git
sudo -H -u "$USER_NAME" git init -q "$T/priv"
sudo -H -u "$USER_NAME" git -C "$T/priv" remote add origin https://github.com/example-user/private-project.git
probe() { printf '{"cwd":"%s","tool_input":{"command":"git push"}}' "$1" \
          | sudo -H -u "$USER_NAME" "$PY" "$DEST/git_guard.py" hook; }
PUB_OUT="$(probe "$T/pub")"
PRIV_OUT="$(probe "$T/priv")"
PP_OUT="$(cd "$T/pub" && sudo -H -u "$USER_NAME" env CLAUDECODE=1 "$HOOKS/pre-push" origin \
          https://github.com/octocat/Hello-World.git </dev/null 2>&1 && echo LET-THROUGH || true)"
rm -rf "$T"
case "$PUB_OUT" in *'"ask"'*) ;; *) echo "SELF-TEST FAILED: public push not caught. User settings left strict."; exit 1;; esac
[ -z "$PRIV_OUT" ] || { echo "SELF-TEST FAILED: private push flagged. User settings left strict."; exit 1; }
case "$PP_OUT" in *LET-THROUGH*) echo "SELF-TEST FAILED: pre-push let a public push through. User settings left strict."; exit 1;; esac
[ "$(git config --system core.hooksPath)" = "$HOOKS" ] || { echo "SELF-TEST FAILED: hooksPath not set."; exit 1; }

echo "== loosening per-user git prompts"
sudo -H -u "$USER_NAME" "$PY" "$SRC/apply_user_settings.py"
echo "DONE. Restart Claude Code sessions to pick it up."
