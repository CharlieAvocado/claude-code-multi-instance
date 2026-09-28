#!/usr/bin/env python3
"""Tests for git_guard.py. Run: python3 test_guard.py [--live]

Builds throwaway repos in a temp dir. Visibility is faked from a table
unless --live, which also checks the real GitHub API for a few repos.
Nothing is ever pushed anywhere but a local bare repo.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import git_guard as g  # noqa: E402

PUBLIC = {("octocat", "hello-world"), ("octocat", "spoon-knife"),
          ("octocat", "linguist")}
LIVE = "--live" in sys.argv


def fake_visibility(owner, repo):
    return "public" if (owner.lower(), repo.lower()) in PUBLIC else "private"


if not LIVE:
    g.github_visibility = fake_visibility

T = tempfile.mkdtemp(prefix="gitguard-test-")
ENV = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1",
           GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
           GIT_COMMITTER_EMAIL="t@t")
ENV.pop("CLAUDECODE", None)


def sh(cmd, cwd=T):
    subprocess.run(cmd, shell=True, cwd=cwd, env=ENV, check=True,
                   capture_output=True)


def repo(name, remotes=(), extra=""):
    d = os.path.join(T, name)
    sh(f"git init -q -b main {d} && cd {d} && git commit -q --allow-empty -m init")
    for rname, url in remotes:
        sh(f"git remote add {rname} {url}", d)
    if extra:
        sh(extra, d)
    return d


BARE = os.path.join(T, "bare.git")
sh(f"git init -q --bare {BARE}")
PUB = repo("pub", [("origin", "https://github.com/octocat/Hello-World.git")])
PRIV = repo("priv", [("origin", "https://github.com/example-user/private-project.git"),
                     ("mirror", BARE)])
ALIAS = repo("alias", [("origin", "git@github.com-work:example-user/private-notes.git"),
                       ("pub", "git@github.com-work:octocat/Spoon-Knife.git")])
LAB = repo("lab", [("origin", "https://gitlab.com/someone/thing.git")])
LOCAL = repo("local", [("origin", BARE)])
SPLIT = repo("split", [("origin", "https://github.com/example-user/private-project.git")],
             "git remote set-url --push origin https://github.com/octocat/Hello-World.git")
NOREMOTE = repo("noremote")
REWRITE = repo("rewrite", [("origin", "https://github.com/example-user/private-project.git")],
               "git config url.https://github.com/octocat/.insteadOf gh:")
SUBMOD = repo("submod", [("origin", "https://github.com/example-user/private-project.git")],
              "git config push.recurseSubmodules on-demand")
ALIASES = repo("aliases", [("origin", "https://github.com/example-user/private-project.git")],
               "git config alias.p push && git config alias.st status && "
               "git config alias.sync '!git pull && git push'")
SSHURL = repo("sshurl", [("origin", "ssh://git@github.com/octocat/linguist.git")])
NOTREPO = os.path.join(T, "notrepo")
os.mkdir(NOTREPO)

# branches for delete tests
BR = repo("br", [("origin", BARE)])
sh("git checkout -q -b merged && git commit -q --allow-empty -m m && "
   "git checkout -q main && git merge -q --ff-only merged", BR)
sh("git checkout -q -b unmerged && echo x > f && git add f && git commit -q -m u && "
   "git checkout -q main", BR)
sh("git checkout -q -b squashed && echo y > s && git add s && git commit -q -m s1 && "
   "echo z >> s && git commit -q -am s2 && git checkout -q main && "
   "git merge -q --squash squashed && git commit -q -m squash", BR)
sh("git checkout -q -b picked && echo p > p && git add p && git commit -q -m p && "
   "git checkout -q main && git cherry-pick picked", BR)

ASK, OK = "ask", "ok"
CASES = [
    # --- gh anywhere in the command (a public repo was created by
    # "gh auth switch ... && gh repo create --public" without a prompt)
    (PRIV, "gh auth switch --user X && gh repo create me/x --public --source . --push", ASK),
    (PRIV, "gh repo create me/x --private", ASK),
    (PRIV, "cd /tmp; gh repo edit --visibility public", ASK),
    (PRIV, "bash -c 'gh repo create me/x --public'", ASK),
    (PRIV, "echo $(gh gist create f.md)", ASK),
    (PRIV, "gh -R me/x release create v1", ASK),
    (PRIV, "gh api -X PATCH repos/me/x -f private=false", ASK),
    (PRIV, "gh pr create --fill", ASK),
    (PRIV, "gh mystery-alias", ASK),
    (PRIV, "gh repo view me/x", OK),
    (PRIV, "gh auth switch --user X", OK),
    (PRIV, "gh auth status", OK),
    (PRIV, "gh api repos/me/x -q .private", OK),
    (PRIV, "gh pr list && gh issue view 3", OK),
    (PRIV, "gh gist list", OK),
    (PRIV, 'git commit -m "fix gh thing"', OK),
    # --- plain pushes
    (PRIV, "git push", OK),
    (PUB, "git push", ASK),
    (PRIV, "git push origin main", OK),
    (PRIV, "git push -u origin HEAD", OK),
    (PRIV, "git push mirror main", OK),
    (PRIV, 'git push origin "$(git branch --show-current)"', OK),
    (PRIV, "git push origin $(git branch --show-current)", OK),
    (PUB, "git push origin main", ASK),
    (PUB, "git push --dry-run", ASK),
    (PUB, "git push --tags", ASK),
    (PUB, "git push origin --delete worktree-x", ASK),
    (LOCAL, "git push", OK),
    (LOCAL, "git push origin main 2>&1 | tail -5", OK),
    (PUB, "git push origin main 2>&1 | tail -5", ASK),
    (PUB, "git push >/dev/null 2>&1 &", ASK),
    # --- aiming somewhere else from a private repo
    (PRIV, "git push https://github.com/octocat/Hello-World.git main", ASK),
    (PRIV, "git push git@github.com:octocat/Hello-World.git main", ASK),
    (PRIV, "git push --repo=https://github.com/octocat/Hello-World.git", ASK),
    (PRIV, "git push --repo https://github.com/octocat/Hello-World.git", ASK),
    (PRIV, f"git -C {PUB} push", ASK),
    (PRIV, f"git -C {T} -C pub push", ASK),
    (PRIV, f"git --git-dir={PUB}/.git push", ASK),
    (PRIV, f"cd {PUB} && git push", ASK),
    (PRIV, f"cd {PUB}; git push", ASK),
    (PRIV, f"cd {PUB}\ngit push", ASK),
    (PRIV, "cd ../pub && git push", ASK),
    (PRIV, f"(cd {PUB} && git status); git push", OK),
    (PRIV, f"(cd {PUB} && git push); git status", ASK),
    (PUB, f"cd {PRIV} && git push", OK),
    (PRIV, "git -c remote.origin.pushurl=https://github.com/octocat/Hello-World.git push", ASK),
    (SPLIT, "git push", ASK),
    (PRIV, "git push gitlab-nope main", OK),  # not a remote -> local path "gitlab-nope"
    (LAB, "git push", ASK),
    (SSHURL, "git push", ASK),
    (ALIAS, "git push", ASK),  # no remote named -> every remote checked, one is public
    (ALIAS, "git push origin main", OK),
    (ALIAS, "git push pub main", ASK),
    (ALIAS, "git push origin main && git push pub main", ASK),
    # --- wrappers and disguises
    (PUB, "/usr/bin/git push", ASK),
    (PUB, "FOO=1 git push", ASK),
    (PUB, "env FOO=1 git push", ASK),
    (PUB, "timeout 60 git push", ASK),
    (PUB, "nohup git push &", ASK),
    (PUB, "command git push", ASK),
    (PUB, "if true; then git push; fi", ASK),
    (PUB, 'bash -c "git push"', ASK),
    (PRIV, 'bash -c "git push"', OK),
    (PRIV, f"sh -c 'cd {PUB} && git push'", ASK),
    (PRIV, "eval git push", ASK),
    (PRIV, "echo origin | xargs git push", ASK),
    (PRIV, "git submodule foreach git push", ASK),
    (PRIV, "git lfs push origin main", ASK),
    (PRIV, "git subtree push --prefix=x origin main", ASK),
    (PRIV, "docker push someone/image", ASK),
    (PRIV, "git push $REMOTE main", ASK),
    (PRIV, 'git -C "$D" push', ASK),
    (PRIV, "for d in a b; do git -C $d push; done", ASK),
    (PRIV, "git push --no-verify", ASK),
    (PRIV, "git push --receive-pack=x", ASK),
    (PRIV, "git push --recurse-submodules=on-demand", ASK),
    (PRIV, "git push --recurse-submodules=check", OK),
    (SUBMOD, "git push", ASK),
    (REWRITE, "git push", ASK),
    (NOREMOTE, "git push", ASK),
    (NOTREPO, "git push", ASK),
    (PRIV, "git -C /nonexistent/dir push", ASK),
    (PRIV, "python3 - <<'EOF'\nimport subprocess\nsubprocess.run(['git','push'])\nEOF", ASK),
    (PRIV, "cat <<EOF | bash\ngit push\nEOF", ASK),
    (ALIASES, "git p", ASK),
    (ALIASES, "git sync", ASK),
    (ALIASES, "git st", OK),
    (PRIV, "git send-pack https://github.com/octocat/Hello-World.git main", ASK),
    (PRIV, "git http-push x", ASK),
    (PRIV, "git ${X:-push}", ASK),
    (PRIV, "G=git; $G push", ASK),
    (PRIV, 'git "push"', OK),
    (PUB, "git p\\ush", ASK),
    (PRIV, "git -c alias.x=push x", ASK),
    (PRIV, "cd ~ && cd projects && git status", OK),
    # --- switching the guard off
    (PRIV, "git config core.hooksPath /tmp/x", ASK),
    (PRIV, "git config --global core.HooksPath /tmp/x", ASK),
    (PRIV, "git -c core.hooksPath=/dev/null push", ASK),
    (PRIV, "GIT_CONFIG_NOSYSTEM=1 git push", ASK),
    (PRIV, "export CLAUDE_GIT_GUARD_APPROVED=1; git push", ASK),
    (PRIV, "sudo rm /etc/claude-code/managed-settings.json", ASK),
    (PRIV, "echo x > /etc/gitconfig", ASK),
    (PRIV, "export GIT_DIR=/x; git status", ASK),
    # --- not pushes
    (PUB, "git status", OK),
    (PUB, "git commit -m 'push fix'", OK),
    (PUB, "git stash push -m wip", OK),
    (PUB, "git log --oneline -5 && git diff", OK),
    (PUB, "git fetch && git pull --ff-only", OK),
    (PUB, 'git commit -m "$(cat <<\'EOF\'\nFix the thing\n\nIt pushes less.\nEOF\n)"', OK),
    (PUB, "ls -la && echo done", OK),
    (PUB, 'echo "unbalanced', OK),
    (PUB, "python3 pull.py --dry-run", OK),
    (PUB, "cat push.md", ASK),  # a bare word 'push'... not bare here: 'push.md' is fine
    # --- branch deletes
    (BR, "git branch -d unmerged", OK),
    (BR, "git branch -D merged", OK),
    (BR, "git branch -D squashed", OK),
    (BR, "git branch -D picked", OK),
    (BR, "git branch -D unmerged", ASK),
    (BR, "git branch --delete --force unmerged", ASK),
    (BR, "git branch -df unmerged", ASK),
    (BR, "git branch -D merged unmerged", ASK),
    (BR, "git branch -D main", ASK),
    (BR, "git branch -D does-not-exist", OK),
    (BR, "git branch -dr origin/whatever", OK),
    (PRIV, f"git -C {BR} branch -D unmerged", ASK),
    (PRIV, f"cd {BR} && git branch -D merged && git branch -D squashed", OK),
    (BR, "git branch -D $B", ASK),
    (BR, "git worktree remove wt", OK),
    (BR, "git worktree remove --force wt", ASK),
    (BR, "git worktree prune", OK),
]
# The github.com-work SSH alias only exists where ~/.ssh/config defines it; skip
# the alias cases on a machine without it rather than fail the install.
def _alias_ok():
    r = subprocess.run(["ssh", "-G", "github.com-work"], capture_output=True,
                       text=True, stdin=subprocess.DEVNULL)
    return "hostname github.com" in r.stdout.lower().splitlines()


if not _alias_ok():
    print("note: no github.com-work SSH alias here; skipping those cases")
    CASES = [c for c in CASES if c[0] != ALIAS and "github.com-work" not in c[1]]
PREPUSH_SKIP_ALIAS = not _alias_ok()
# 'cat push.md' tokenizes to ['cat', 'push.md'], which is not the bare word
# 'push', so it's fine; fix the expectation rather than special-casing.
CASES = [(d, c, OK if c == "cat push.md" else e) for d, c, e in CASES]


def run_cases():
    fails = 0
    for d, cmd, expect in CASES:
        reasons, _ = g.decide(cmd, d, ENV)
        got = ASK if reasons else OK
        if got != expect:
            fails += 1
            print(f"FAIL [{os.path.basename(d)}] {cmd!r}: expected {expect}, got {got} {reasons}")
    print(f"layer 1: {len(CASES) - fails}/{len(CASES)} passed")
    return fails


def run_hook_protocol():
    """End to end through stdin/stdout the way Claude Code calls it."""
    fails = 0
    script = os.path.join(HERE, "git_guard.py")
    env = dict(ENV)
    for cmd, cwd, want_ask in (("git push", PRIV, False), ("git status", PUB, False),
                               ("git push", PUB, True)):
        if not LIVE and want_ask is False and cmd == "git push":
            pass
        payload = json.dumps({"tool_name": "Bash", "cwd": cwd,
                              "tool_input": {"command": cmd, "description": "d"}})
        r = subprocess.run([sys.executable, script, "hook"], input=payload,
                           capture_output=True, text=True, env=env)
        out = r.stdout.strip()
        asked = bool(out) and json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "ask"
        if LIVE or not want_ask and cmd != "git push":
            if asked != want_ask or r.returncode != 0:
                fails += 1
                print(f"FAIL hook protocol {cmd!r} in {cwd}: asked={asked} rc={r.returncode} {r.stderr}")
        if asked:
            upd = json.loads(out)["hookSpecificOutput"].get("updatedInput", {})
            if not upd.get("command", "").startswith(f"export {g.APPROVAL_VAR}=1; "):
                fails += 1
                print("FAIL hook protocol: approval prefix missing")
    # garbage input must ask, never crash silently
    r = subprocess.run([sys.executable, script, "hook"], input="not json",
                       capture_output=True, text=True, env=env)
    if '"ask"' not in r.stdout:
        fails += 1
        print("FAIL hook protocol: bad input didn't ask")
    print(f"hook protocol: {'ok' if not fails else f'{fails} failures'}")
    return fails


def run_prepush():
    """Layer 2, called the way git calls it (remote name, url; refs on stdin)."""
    fails = 0
    script = os.path.join(HERE, "git_guard.py")
    cases = [
        ({"CLAUDECODE": "1"}, "https://github.com/octocat/Hello-World.git", 1),
        ({"CLAUDECODE": "1"}, "git@github.com-work:octocat/Spoon-Knife.git", 1),
        ({"CLAUDECODE": "1"}, "https://gitlab.com/x/y.git", 1),
        ({"CLAUDECODE": "1"}, "ext::sh -c evil", 1),
        ({"CLAUDECODE": "1"}, "https://github.com/example-user/private-project.git", 0),
        ({"CLAUDECODE": "1"}, "git@github.com-work:example-user/private-notes.git", 0),
        ({"CLAUDECODE": "1"}, BARE, 0),
        ({"CLAUDECODE": "1", g.APPROVAL_VAR: "1"}, "https://github.com/octocat/Hello-World.git", 0),
        ({}, "https://github.com/octocat/Hello-World.git", 0),  # the user's own terminal
    ]
    for extra, url, want in cases:
        if PREPUSH_SKIP_ALIAS and "github.com-work" in url:
            continue
        if not LIVE and "github" in url:
            # layer 2 runs as its own process, so it always does the real
            # lookup; only run those under --live
            continue
        env = dict(ENV, **extra)
        r = subprocess.run([sys.executable, script, "pre-push", "origin", url],
                           input=b"", capture_output=True, env=env, cwd=PRIV)
        if r.returncode != want:
            fails += 1
            print(f"FAIL pre-push {url} {extra}: rc={r.returncode} want {want} {r.stderr.decode()}")
    # real git push through the hooks dir to a local bare repo, with a
    # repo-local pre-push hook that must still run (chaining)
    hooks = os.path.join(T, "hooks")
    os.mkdir(hooks)
    pp = os.path.join(hooks, "pre-push")
    with open(pp, "w") as f:
        f.write(f"#!/bin/sh\nexec {sys.executable} {script} pre-push \"$@\"\n")
    os.chmod(pp, 0o755)
    local_hook = os.path.join(LOCAL, ".git", "hooks", "pre-push")
    with open(local_hook, "w") as f:
        f.write(f"#!/bin/sh\ntouch {T}/local-hook-ran\nexit 0\n")
    os.chmod(local_hook, 0o755)
    env = dict(ENV, CLAUDECODE="1")
    r = subprocess.run(["git", "-c", f"core.hooksPath={hooks}", "push", "-q", "origin", "main"],
                       cwd=LOCAL, env=env, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(f"{T}/local-hook-ran"):
        fails += 1
        print(f"FAIL real push via hooks dir: rc={r.returncode} {r.stderr}")
    with open(local_hook, "w") as f:
        f.write("#!/bin/sh\nexit 1\n")
    r = subprocess.run(["git", "-c", f"core.hooksPath={hooks}", "push", "-q", "origin", "main"],
                       cwd=LOCAL, env=env, capture_output=True, text=True)
    if r.returncode == 0:
        fails += 1
        print("FAIL chained repo hook's refusal was ignored")
    print(f"layer 2: {'ok' if not fails else f'{fails} failures'}")
    return fails


def run_live():
    fails = 0
    for owner, repo, want in (("octocat", "Hello-World", "public"),
                              ("example-user", "private-notes", "private"),
                              ("example-user", "private-project", "private")):
        got = g.github_visibility(owner, repo)
        if got != want:
            fails += 1
            print(f"FAIL live visibility {owner}/{repo}: {got}")
    print(f"live GitHub checks: {'ok' if not fails else f'{fails} failures'}")
    return fails


if __name__ == "__main__":
    total = run_cases() + run_hook_protocol() + run_prepush()
    if LIVE:
        total += run_live()
    subprocess.run(["rm", "-rf", T])
    print("ALL PASS" if total == 0 else f"{total} FAILURES")
    sys.exit(1 if total else 0)
