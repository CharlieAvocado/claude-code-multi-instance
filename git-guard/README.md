# git-guard

Lets Claude Code run everyday git without approval prompts, but never make anything public
without the user's OK. Built as part of the author's custom Claude Code dashboard setup; it
has no dependency on the dashboard and runs standalone.

- **Everyday git is allowed:** commit, push, pull, merge, checkout, branch.
- **A push to a public repo asks.** Before each push, `git_guard.py` asks the GitHub API,
  logged out, whether the destination is visible. Only a confirmed-private GitHub repo (the
  anonymous API returns 404) or a local path goes through silently. Anything uncertain asks:
  unknown hosts, network errors, variables, aliases, `--no-verify`.
- **Second layer:** a system-wide git `pre-push` hook refuses a public push from inside a
  Claude session unless the user approved that command. This catches pushes buried in
  scripts.
- **Branch deletes:** `git branch -D` goes through when everything on the branch is already
  on main (merged, squashed or cherry-picked), and asks only when work would be lost.
- **Claude can't change it.** It installs root-owned as Claude Code managed settings, which
  take precedence over user settings: `/etc/claude-code/` on Linux,
  `/Library/Application Support/ClaudeCode/` on macOS. Any command touching `hooksPath`, the
  guard's files or its approval variable asks.
- **`gh` commands that create or publish ask,** wherever they appear: `gh repo create`,
  visibility edits, gists, releases, PRs, writing `gh api` calls, and any `gh` alias or
  extension. The guard checks every command in a line, including after `&&` and inside
  `bash -c "..."`, because Claude Code's own ask rules only match the start of the line.
- Force-push, `git clean`, `filter-branch` and similar stay denied.

## Install or update

Run once per machine, from a normal terminal (not inside Claude):

    sudo sh git-guard/install.sh

It runs the tests (including a live check against the GitHub API), installs, self-tests the
installed copy, and only then relaxes the per-user git prompts in every
`~/.claude*/settings.json`, backing each up as `settings.json.bak-git-guard`. If any check
fails it stops and leaves the settings strict. Restart Claude Code sessions afterwards.

The install sets `git config --system core.hooksPath`, which hides each repo's own
`.git/hooks`. The `chain` script, linked under every hook name, runs the repo's own hook of
the same name so existing hooks keep working.

## Tests

    python3 git-guard/test_guard.py          # visibility faked from a table
    python3 git-guard/test_guard.py --live   # also queries the real GitHub API

The examples use public `octocat/*` repos and a nonexistent `example-user/*` repo as the
private stand-in (the anonymous API answers 404 either way). Cases using an SSH host alias
(`github.com-work`) are skipped unless `~/.ssh/config` defines one.

## Limits

- A `! git push` typed at the Claude prompt counts as a Claude-session push, so layer 2
  refuses public repos there. Push public repos from a normal terminal, or let Claude run it
  and approve.
- A deliberately disguised push (for example a script that clears the session variable)
  could get past. Ordinary and accidental pushes are covered.
- GitHub only. Pushes to other hosts always ask.
