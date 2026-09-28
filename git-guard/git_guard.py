#!/usr/bin/env python3
"""claude-git-guard: stops Claude Code from pushing to a PUBLIC GitHub repo
without the user's say-so, and from force-deleting a branch that holds work
not already on main.

Installed root-owned (see install.sh), so Claude can't edit or remove it.
Two entry points:

  git_guard.py hook       Layer 1. Claude Code PreToolUse hook (managed
                          settings). Reads the tool call on stdin; prints an
                          "ask" decision when a command needs the user.
  git_guard.py pre-push   Layer 2. git pre-push hook (system core.hooksPath).
                          Refuses a push to a public repo from inside a
                          Claude session unless the user approved it in layer 1.

The one rule everywhere: when in doubt, ask (layer 1) or refuse (layer 2).
A push only goes through silently when every destination is positively
confirmed private (anonymous GitHub API 404) or a local path.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.dont_write_bytecode = True

APPROVAL_VAR = "CLAUDE_GIT_GUARD_APPROVED"
GITHUB_API = "https://api.github.com/repos/{}/{}"
GITHUB_HOSTS = {"github.com", "www.github.com", "ssh.github.com"}
NET_TIMEOUT = 8
GIT_TIMEOUT = 20
MAX_DEPTH = 4

# Any mention of these asks, whatever the command: they are the ways to
# switch the guard off or forge an approval.
TRIPWIRES = [
    "hookspath",
    "git_config_nosystem",
    "git_config_system",
    "git_config_count",
    "git_config_parameters",
    APPROVAL_VAR.lower(),
    "/etc/claude-code",
    "/etc/gitconfig",
    "application support/claudecode",
    "managed-settings",
]

SHELL_KEYWORDS = {"if", "then", "else", "elif", "fi", "do", "done", "while",
                  "until", "!", "{", "}", "time", "esac"}
SKIP_WHOLE = {"for", "case", "select", "function"}
REDIRECTS = {"<", ">", ">>", "<<", "<<-", "<<<", ">&", "<&", "&>", "&>>",
             ">|", "<>", ">>&"}
PUNCT = "();<>|&\n"

# git subcommands that never push and can't be aliases (aliases can't
# shadow builtins). Anything else gets an alias lookup.
SAFE_SUBCOMMANDS = {
    "add", "am", "apply", "archive", "bisect", "blame", "branch", "cat-file",
    "checkout", "cherry", "cherry-pick", "clean", "clone", "commit", "config",
    "describe", "diff", "fetch", "for-each-ref", "format-patch", "fsck", "gc",
    "grep", "hash-object", "help", "init", "log", "ls-files", "ls-remote",
    "ls-tree", "merge", "merge-base", "mv", "name-rev", "notes", "pull",
    "push", "rebase", "reflog", "remote", "reset", "restore", "rev-list",
    "rev-parse", "revert", "rm", "shortlog", "show", "show-ref", "stash",
    "status", "submodule", "switch", "symbolic-ref", "tag", "update-index",
    "var", "version", "worktree",
}
PUSH_PLUMBING = {"send-pack", "http-push", "remote-ext", "remote-fd"}
GLOBAL_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
GLOBAL_OPTS_NO_VALUE = {"-p", "-P", "--paginate", "--no-pager", "--bare",
                        "--no-replace-objects", "--literal-pathspecs",
                        "--glob-pathspecs", "--noglob-pathspecs",
                        "--icase-pathspecs", "--no-optional-locks",
                        "--no-advice"}


class Unsure(Exception):
    """The guard can't be certain. Always resolves to ask / refuse."""


# --------------------------------------------------------------- visibility

_vis_cache = {}


def github_visibility(owner, repo):
    """'private' or 'public', judged the way a stranger would see it."""
    key = (owner.lower(), repo.lower())
    if key in _vis_cache:
        return _vis_cache[key]
    req = urllib.request.Request(
        GITHUB_API.format(urllib.parse.quote(owner), urllib.parse.quote(repo)),
        headers={"User-Agent": "claude-git-guard",
                 "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=NET_TIMEOUT) as r:
            data = json.load(r)
        result = "private" if data.get("private") is True else "public"
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise Unsure(f"GitHub answered HTTP {e.code} when checking "
                         f"{owner}/{repo}")
        result = "private"
    except Exception as e:
        raise Unsure(f"couldn't reach GitHub to check {owner}/{repo} "
                     f"({e.__class__.__name__})")
    _vis_cache[key] = result
    return result


def ssh_hostname(alias):
    if not alias or alias.startswith("-"):
        raise Unsure(f"odd SSH host {alias!r}")
    try:
        r = subprocess.run(["ssh", "-G", alias], capture_output=True,
                           text=True, timeout=10, stdin=subprocess.DEVNULL)
    except Exception as e:
        raise Unsure(f"couldn't resolve SSH host {alias} ({e.__class__.__name__})")
    for line in r.stdout.splitlines():
        k, _, v = line.partition(" ")
        if k.lower() == "hostname" and v.strip():
            return v.strip().lower()
    raise Unsure(f"couldn't resolve SSH host {alias}")


def github_path(path, url):
    p = path.strip().strip("/")
    if p.endswith(".git"):
        p = p[:-4]
    parts = p.split("/")
    if len(parts) != 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", x) for x in parts):
        raise Unsure(f"can't read owner/repo from {url}")
    return parts


def classify_url(url):
    """Return ('local'|'private'|'public', label). Raises Unsure."""
    u = (url or "").strip()
    if not u:
        raise Unsure("empty remote URL")
    if "::" in u:
        raise Unsure(f"remote helper URL {u}")
    m = re.match(r"^([A-Za-z][A-Za-z0-9+.-]*)://", u)
    if m:
        scheme = m.group(1).lower()
        if scheme == "file":
            return "local", u
        if scheme not in ("http", "https", "ssh", "git", "git+ssh", "ssh+git"):
            raise Unsure(f"unknown transport {scheme}:// in {u}")
        sp = urllib.parse.urlsplit(u)
        host = (sp.hostname or "").lower()
        if scheme in ("ssh", "git+ssh", "ssh+git"):
            host = ssh_hostname(host)
        path = sp.path
    else:
        colon, slash = u.find(":"), u.find("/")
        if colon > 0 and (slash == -1 or colon < slash):
            hostpart, path = u[:colon], u[colon + 1:]
            host = ssh_hostname(hostpart.rsplit("@", 1)[-1].strip("[]"))
        else:
            return "local", u
    if host not in GITHUB_HOSTS:
        raise Unsure(f"{host or u} isn't GitHub, so its visibility can't be checked")
    owner, repo = github_path(path, u)
    return github_visibility(owner, repo), f"{owner}/{repo}"


# ------------------------------------------------------------------- git io

def git(base, args, cwd, env):
    try:
        return subprocess.run(base + args, cwd=cwd, env=env, capture_output=True,
                              text=True, timeout=GIT_TIMEOUT,
                              stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        raise Unsure(f"folder {cwd} doesn't exist")
    except Exception as e:
        raise Unsure(f"git query failed ({e.__class__.__name__})")


def require_repo(base, cwd, env):
    if not os.path.isdir(cwd):
        raise Unsure(f"folder {cwd} doesn't exist")
    if git(base, ["rev-parse", "--git-dir"], cwd, env).returncode != 0:
        raise Unsure(f"{cwd} isn't a git repo as far as the guard can tell")


def config_lines(base, cwd, env, regexp):
    r = git(base, ["config", "--get-regexp", regexp], cwd, env)
    if r.returncode not in (0, 1):
        raise Unsure("couldn't read git config")
    out = []
    for line in r.stdout.splitlines():
        k, _, v = line.partition(" ")
        out.append((k, v))
    return out


def push_urls(base, cwd, env, remote):
    require_repo(base, cwd, env)
    if config_lines(base, cwd, env, r"^url\..*\.(push)?insteadof$"):
        raise Unsure("URL rewriting (insteadOf) is configured")
    for _, v in config_lines(base, cwd, env, r"^push\.recursesubmodules$"):
        if v.lower() not in ("no", "false", "check"):
            raise Unsure("push also pushes submodules (push.recurseSubmodules)")
    r = git(base, ["remote"], cwd, env)
    if r.returncode != 0:
        raise Unsure("couldn't list remotes")
    remotes = set(r.stdout.split())
    names, urls = set(), []
    if remote is None:
        # No remote named: check every place git could send it.
        names |= remotes
        for _, v in config_lines(base, cwd, env,
                                 r"^(remote\.pushdefault|branch\..*\.(push)?remote)$"):
            if v in remotes:
                names.add(v)
            elif v != ".":
                urls.append(v)
        if not names and not urls:
            raise Unsure("no remote configured")
    elif remote in remotes:
        names.add(remote)
    else:
        urls.append(remote)
    for n in sorted(names):
        r = git(base, ["remote", "get-url", "--push", "--all", n], cwd, env)
        got = r.stdout.split("\n")
        got = [x.strip() for x in got if x.strip()]
        if r.returncode != 0 or not got:
            raise Unsure(f"couldn't read the push URL for remote {n}")
        urls += got
    return urls


# ------------------------------------------------------------- shell parsing

HEREDOC_RE = re.compile(r"(?<!<)<<(-?)[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2(?!<)")
GIT_PUSH_RE = re.compile(r"\bgit\b[\s\S]*\bpush\b")
GIT_BRANCH_DEL_RE = re.compile(r"\bgit\b[\s\S]*\bbranch\b[\s\S]*(-[A-Za-z]*D|--force|-[A-Za-z]*f)")
GIT_WORKTREE_RE = re.compile(r"\bgit\b[\s\S]*\bworktree\b[\s\S]*\bremove\b")
GH_RE = re.compile(r"\bgh\b")

# gh commands that create, publish or change something on GitHub. Checked on
# every simple command, so they ask even after && or inside bash -c "...";
# the managed-settings ask rules only match the start of the whole line.
GH_ASK = {
    "repo": {"create", "new", "edit", "fork", "sync", "delete", "rename",
             "archive", "unarchive", "deploy-key"},
    "pr": {"create", "new", "merge"},
    "gist": {"create", "new", "edit", "delete", "rename", "clone"},
    "release": None, "secret": None, "variable": None, "workflow": None,
    "ssh-key": None, "gpg-key": None, "alias": None, "extension": None,
    "auth": {"login", "refresh", "setup-git", "token"},
}
# Top-level gh commands that never publish. Anything else (including aliases
# and extensions, which could expand to anything) asks.
GH_KNOWN = set(GH_ASK) | {"api", "browse", "codespace", "issue", "org", "project",
                          "cache", "run", "label", "ruleset", "attestation",
                          "completion", "config", "search", "status", "help",
                          "--version", "version", "-h", "--help"}
GH_API_WRITE = ("-X", "--method", "-f", "-F", "--field", "--raw-field", "--input")


def strip_heredocs(cmd):
    """Remove heredoc bodies (they're data, not commands) but ask if one
    looks like it feeds a git push to something."""
    out, pos = [], 0
    while True:
        m = HEREDOC_RE.search(cmd, pos)
        if not m:
            out.append(cmd[pos:])
            return "".join(out)
        nl = cmd.find("\n", m.end())
        if nl == -1:
            out.append(cmd[pos:])
            return "".join(out)
        tabs, delim = m.group(1) == "-", m.group(3)
        end_re = re.compile(r"^" + (r"\t*" if tabs else "") + re.escape(delim) + r"$",
                            re.M)
        e = end_re.search(cmd, nl + 1)
        if not e:
            raise Unsure("unterminated heredoc")
        body = cmd[nl + 1:e.start()]
        if GIT_PUSH_RE.search(body):
            raise Unsure("a heredoc contains a git push")
        out.append(cmd[pos:nl + 1])
        pos = e.end()


def tokenize(cmd):
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=PUNCT)
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    lex.commenters = ""
    return list(lex)


def is_op(tok):
    return tok != "" and all(c in PUNCT for c in tok)


def has_expansion(s):
    return "$" in s or "`" in s


def expand_path(p, cwd):
    p = os.path.expanduser(p)
    return os.path.normpath(os.path.join(cwd, p))


class Analysis:
    def __init__(self, cwd, env, visibility):
        self.cwd = cwd
        self.env = env
        self.reasons = []
        self.involves_push = False
        self.visibility = visibility

    def add(self, reason):
        if reason not in self.reasons:
            self.reasons.append(reason)


def split_commands(tokens):
    """Yield (words, op_before) for each simple command, dropping redirects."""
    words, prev_op, i = [], ";", 0
    while i < len(tokens):
        t = tokens[i]
        if t in REDIRECTS or (is_op(t) and t.strip("\n") in REDIRECTS):
            if words and words[-1].isdigit():
                words.pop()
            i += 2  # the redirect target
            continue
        if is_op(t):
            if words:
                yield words, prev_op
            words, prev_op = [], t
            i += 1
            continue
        words.append(t)
        i += 1
    if words:
        yield words, prev_op


def analyze(cmd, a, depth=0):
    """Fill a.reasons for everything in cmd that needs the user. Returns the
    number of git pushes it positively recognised."""
    if depth > MAX_DEPTH:
        raise Unsure("command nests too deep to check")
    low = cmd.lower()
    for t in TRIPWIRES:
        if t in low:
            raise Unsure(f"command touches the guard's own settings ({t})")
    cmd = strip_heredocs(cmd)
    try:
        tokens = tokenize(cmd)
    except ValueError:
        if re.search(r"push|branch|worktree|\bgh\b", cmd, re.I):
            raise Unsure("couldn't parse the command")
        return 0

    cwd_stack, cwd = [], a.cwd
    pushes, explained_push = 0, 0
    total_push_tokens = sum(1 for t in tokens if t == "push")

    for words, op in split_commands(tokens):
        # subshell bookkeeping: "(" opens, ")" closes
        if "(" in op:
            cwd_stack.append(cwd)
        if ")" in op and cwd_stack:
            cwd = cwd_stack.pop()

        # quoted strings that are themselves commands (bash -c "...", $(...))
        for w in words:
            if any(c in w for c in " \t\n;&|()") and (
                    GIT_PUSH_RE.search(w) or GIT_BRANCH_DEL_RE.search(w)
                    or GIT_WORKTREE_RE.search(w) or GH_RE.search(w)):
                sub = Analysis(cwd, a.env, a.visibility)
                n = analyze(w, sub, depth + 1)
                for r in sub.reasons:
                    a.add(r)
                a.involves_push |= sub.involves_push
                if GIT_PUSH_RE.search(w) and n == 0:
                    raise Unsure("a quoted string mentions git push but can't be checked")

        w = list(words)
        while w and w[0] in SHELL_KEYWORDS:
            w.pop(0)
        if not w or w[0] in SKIP_WHOLE:
            continue

        env = dict(a.env)
        while w and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w[0]):
            k, _, v = w.pop(0).partition("=")
            if k.startswith("GIT_") and has_expansion(v):
                raise Unsure(f"{k} is set from a variable")
            env[k] = v
        # wrappers that run the rest of the line as a command
        while w:
            if w[0] in ("command", "builtin", "exec", "nohup", "nice", "time", "setsid"):
                w.pop(0)
            elif w[0] == "timeout":
                w.pop(0)
                while w and w[0].startswith("-"):
                    w.pop(0)
                if w:
                    w.pop(0)
            elif w[0] == "env":
                w.pop(0)
                while w and (w[0].startswith("-") or "=" in w[0]):
                    if w[0].startswith("-"):
                        raise Unsure("env with options")
                    k, _, v = w.pop(0).partition("=")
                    if k.startswith("GIT_") and has_expansion(v):
                        raise Unsure(f"{k} is set from a variable")
                    env[k] = v
            elif w[0] == "sudo":
                if "push" in w or "branch" in w:
                    raise Unsure("git run through sudo")
                w = []
            else:
                break
        if not w:
            continue
        head = w[0]

        if head in ("export", "declare", "typeset", "local", "readonly"):
            if any(x.startswith("GIT_") for x in w[1:]):
                raise Unsure("changes git's environment for the rest of the command")
            continue
        if head in ("cd", "pushd"):
            args = [x for x in w[1:] if not x.startswith("-") or x == "-"]
            if not args:
                cwd = os.path.expanduser("~")
            elif args[0] == "-" or has_expansion(args[0]) or "*" in args[0]:
                cwd = None
            else:
                cwd = expand_path(args[0], cwd) if cwd else None
            continue
        if head == "popd":
            cwd = None
            continue

        if os.path.basename(head) == "gh" and not has_expansion(head):
            check_gh(w, a)
            continue
        if os.path.basename(head) != "git" or has_expansion(head):
            continue
        n_push, n_explained = git_command(w, cwd, env, a)
        pushes += n_push
        explained_push += n_explained

    if total_push_tokens > explained_push:
        raise Unsure("'push' appears in a way the guard can't check")
    return pushes


def check_gh(w, a):
    """Ask before any gh command that could create or publish something."""
    args = w[1:]
    while args and args[0] in ("-R", "--repo"):
        args = args[2:]
    if not args:
        return
    top = args[0]
    if has_expansion(top):
        a.add("gh subcommand comes from a variable")
        return
    if top not in GH_KNOWN:
        a.add(f"gh {top} is an alias, extension or unknown command")
        return
    if top == "api":
        if any(x.startswith(GH_API_WRITE) for x in args[1:]):
            a.add("gh api call that can change something on GitHub")
        return
    subs = GH_ASK.get(top, set())
    sub = args[1] if len(args) > 1 else ""
    if subs is None or sub in subs:
        a.add(f"gh {top} {sub}".strip() + " can create or publish something on GitHub")


def git_command(w, cwd, env, a):
    """Handle one git invocation. Returns (pushes_recognised, push_tokens_explained)."""
    base, i = ["git"], 1
    relevant = "push" in w or "branch" in w or "worktree" in w
    while i < len(w):
        t = w[i]
        if t in GLOBAL_OPTS_WITH_VALUE:
            if i + 1 >= len(w):
                raise Unsure(f"git {t} without a value")
            v = w[i + 1]
            if has_expansion(v) and relevant:
                raise Unsure(f"git {t} {v} uses a variable")
            if t in ("-C", "--git-dir", "--work-tree"):
                v = os.path.expanduser(v)
            base += [t, v]
            i += 2
        elif any(t.startswith(o + "=") for o in ("--git-dir", "--work-tree", "--namespace")):
            if has_expansion(t) and relevant:
                raise Unsure(f"git {t} uses a variable")
            k, _, v = t.partition("=")
            base.append(k + "=" + os.path.expanduser(v))
            i += 1
        elif t in GLOBAL_OPTS_NO_VALUE:
            i += 1
        elif t.startswith("-"):
            if relevant:
                raise Unsure(f"unfamiliar git option {t}")
            return 0, 0
        else:
            break
    if i >= len(w):
        return 0, 0
    sub, args = w[i], w[i + 1:]
    if has_expansion(sub):
        raise Unsure(f"git subcommand comes from a variable ({sub})")
    if sub in PUSH_PLUMBING:
        raise Unsure(f"git {sub} pushes without going through git push")

    if sub == "push":
        a.involves_push = True
        if cwd is None:
            raise Unsure("can't tell which folder the push runs in")
        check_push(base, args, cwd, env, a)
        return 1, 1 + args.count("push")  # e.g. a branch literally named push
    if sub == "stash":
        return 0, (1 if args[:1] == ["push"] else 0)
    if sub == "branch":
        check_branch_delete(base, args, cwd, env, a)
        return 0, 0
    if sub == "worktree":
        if args[:1] == ["remove"] and any(x in ("--force", "-f") or
                                          re.fullmatch(r"-[a-z]*f[a-z]*", x) for x in args[1:]):
            a.add("git worktree remove --force can throw away uncommitted work")
        return 0, 0
    if sub not in SAFE_SUBCOMMANDS:
        if cwd is None:
            raise Unsure(f"can't check git alias {sub}")
        r = git(base, ["config", "--get", f"alias.{sub}"], cwd, env)
        if r.returncode == 0:
            val = r.stdout.strip()
            if val.startswith("!") or re.search(r"\bpush\b", val):
                raise Unsure(f"git alias {sub} runs: {val}")
    return 0, 0


def check_push(base, args, cwd, env, a):
    for x in base + args[:1]:
        if has_expansion(x):
            raise Unsure(f"push target uses a variable ({x})")
    remote, repo_opt, i, opts_done = None, None, 0, False
    positional = []
    while i < len(args):
        t = args[i]
        if not opts_done and t == "--":
            opts_done = True
        elif not opts_done and t.startswith("--repo="):
            repo_opt = t[len("--repo="):]
        elif not opts_done and t == "--repo":
            if i + 1 >= len(args):
                raise Unsure("--repo without a value")
            repo_opt = args[i + 1]
            i += 1
        elif not opts_done and t == "--no-verify":
            raise Unsure("--no-verify switches off the push check")
        elif not opts_done and (t.startswith("--receive-pack") or t.startswith("--exec")):
            raise Unsure(f"push with {t}")
        elif not opts_done and t.startswith("--recurse-submodules"):
            if t.partition("=")[2] not in ("no", "check"):
                raise Unsure("push also pushes submodules")
        elif not opts_done and t in ("-o", "--push-option"):
            i += 1
        elif not opts_done and t.startswith("-") and t != "-":
            if not t.startswith("--") and t.endswith("o"):
                i += 1  # clustered short options ending in -o take a value
        else:
            positional.append(t)
        i += 1
    if positional:
        remote = positional[0]
    elif repo_opt is not None:
        remote = repo_opt
    if remote is not None and has_expansion(remote):
        raise Unsure(f"push target uses a variable ({remote})")
    for url in push_urls(base, cwd, env, remote):
        vis, label = classify_url(url)
        if vis == "public":
            a.add(f"pushes to PUBLIC GitHub repo {label}")


def check_branch_delete(base, args, cwd, env, a):
    delete = force = remote = False
    names, opts_done = [], False
    for t in args:
        if not opts_done and t == "--":
            opts_done = True
        elif not opts_done and t.startswith("--"):
            delete |= t == "--delete"
            force |= t == "--force"
            remote |= t == "--remotes"
        elif not opts_done and t.startswith("-") and len(t) > 1:
            flags = t[1:]
            delete |= "d" in flags or "D" in flags
            force |= "D" in flags or "f" in flags
            remote |= "r" in flags
        else:
            names.append(t)
    if not (delete and force) or remote or not names:
        return
    if cwd is None:
        raise Unsure("can't tell which repo the branch delete runs in")
    require_repo(base, cwd, env)
    default = None
    for cand in ("main", "master"):
        if git(base, ["rev-parse", "--verify", "--quiet", f"refs/heads/{cand}"],
               cwd, env).returncode == 0:
            default = cand
            break
    if default is None:
        raise Unsure("repo has no main/master branch to compare against")
    for n in names:
        if has_expansion(n) or any(c in n for c in "*?["):
            raise Unsure(f"branch name {n} uses a variable or wildcard")
        ref = f"refs/heads/{n}"
        if git(base, ["rev-parse", "--verify", "--quiet", ref + "^{commit}"],
               cwd, env).returncode != 0:
            continue  # doesn't exist; git will just error
        if n == default:
            a.add(f"force-deletes {default} itself")
            continue
        if git(base, ["merge-base", "--is-ancestor", ref, f"refs/heads/{default}"],
               cwd, env).returncode == 0:
            continue
        # squash-merged or cherry-picked: merging it would change nothing
        mt = git(base, ["merge-tree", "--write-tree", f"refs/heads/{default}", ref],
                 cwd, env)
        tree = git(base, ["rev-parse", f"refs/heads/{default}^{{tree}}"], cwd, env)
        if (mt.returncode == 0 and tree.returncode == 0
                and mt.stdout.split("\n")[0].strip() == tree.stdout.strip()):
            continue
        a.add(f"branch {n} has work that isn't on {default}; force-deleting loses it")


# -------------------------------------------------------------- entry points

def decide(command, cwd, env=None, visibility=None):
    """Return (reasons, involves_push). Empty reasons = no objection."""
    a = Analysis(cwd, dict(os.environ if env is None else env), visibility)
    try:
        analyze(command, a)
    except Unsure as e:
        a.add(str(e))
        a.involves_push = a.involves_push or bool(re.search(r"push", command))
    return a.reasons, a.involves_push


def hook_main():
    try:
        data = json.load(sys.stdin)
        tool_input = data.get("tool_input") or {}
        command = tool_input.get("command")
        if not isinstance(command, str):
            return 0
        cwd = data.get("cwd") or os.getcwd()
        reasons, involves_push = decide(command, cwd)
    except Exception as e:  # a bug in the guard must never wave a push through
        reasons, involves_push, tool_input = [f"guard error ({e!r})"], True, None
    if not reasons:
        return 0
    out = {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": "git guard: " + "; ".join(reasons),
    }}
    if involves_push and tool_input and isinstance(tool_input.get("command"), str):
        # The user's approval here is what lets layer 2 pass this one command.
        updated = dict(tool_input)
        updated["command"] = f"export {APPROVAL_VAR}=1; " + tool_input["command"]
        out["hookSpecificOutput"]["updatedInput"] = updated
    print(json.dumps(out))
    return 0


def chain_repo_hook(name, argv, stdin_data):
    """Run the repo's own hook of the same name, since core.hooksPath hides it."""
    r = subprocess.run(["git", "rev-parse", "--git-common-dir"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return 0
    hook = os.path.join(r.stdout.strip(), "hooks", name)
    if os.path.isfile(hook) and os.access(hook, os.X_OK):
        return subprocess.run([hook] + list(argv), input=stdin_data).returncode
    return 0


def prepush_main(argv):
    stdin_data = sys.stdin.buffer.read()
    if os.environ.get("CLAUDECODE") == "1" and os.environ.get(APPROVAL_VAR) != "1":
        url = argv[1] if len(argv) > 1 else ""
        try:
            vis, label = classify_url(url)
            problem = f"{label} is a PUBLIC GitHub repo" if vis == "public" else None
        except Unsure as e:
            problem = str(e)
        if problem:
            sys.stderr.write(
                "claude-git-guard: push refused. " + problem + ".\n"
                "Pushes from a Claude session to a repo that isn't confirmed "
                "private need the user's OK: run it as a plain `git push` "
                "command so she's asked, or she can push from her own terminal.\n")
            return 1
    return chain_repo_hook("pre-push", argv, stdin_data)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "hook":
        sys.exit(hook_main())
    if mode == "pre-push":
        sys.exit(prepush_main(sys.argv[2:]))
    sys.stderr.write("usage: git_guard.py hook | pre-push <remote> <url>\n")
    sys.exit(2)
