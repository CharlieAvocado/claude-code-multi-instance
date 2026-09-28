# Instructions for Claude: set up this method

You are Claude Code, and the user has handed you this file. Follow it to set up their machine
(or machines) using the method in this repo. Read `README.md` and `docs/profile-anatomy.md`
before starting; `docs/lessons.md` explains why each rule below exists.

## Ground rules

- **Plan first.** Gather facts, ask the questions below, then show the user a written plan
  and wait for approval before changing anything.
- **Ask one question at a time,** and give a recommendation with each.
- **Never delete or move existing Claude Code data.** Copy, and keep the original until the
  user has confirmed the new setup works. Back up every file before editing it
  (`cp file file.bak-<date>`), including shell startup files and `settings.json`.
- **Don't run `sudo` yourself.** Write the command out, say which machine it runs on, and
  let the user run it.
- **Never create a repo, change a repo's visibility, or publish anything** without the user
  saying yes to that exact action. Default anything new to private.
- **Label every command with its machine** when more than one machine is involved, and give
  commands as single lines the user can paste into a normal terminal (never with a leading
  `!`).
- **Verify, don't assume.** A profile can look fine while missing its settings. Finish every
  step with the checks in "Verify" below.

## 1. Gather facts (read-only)

On each machine the user wants set up, find out:

- The OS and shell (`uname`, `echo $SHELL`), and which startup file the shell reads
  (`~/.zshrc`, `~/.bashrc`).
- Which Claude Code config directories exist: `ls -d ~/.claude*`, and whether
  `CLAUDE_CONFIG_DIR` is set anywhere (`env`, the startup file).
- For each one, run `scripts/verify-profile.sh <dir>` and note: transcripts, settings rules,
  hooks, `cleanupPeriodDays`, enabled plugins.
- Where the user keeps projects (one parent folder, or scattered), and whether they're git
  repos.
- Whether `~/.claude/CLAUDE.md` exists and what it says.

## 2. Ask the user (one at a time)

1. **One machine or two?** If two, which is local (where they edit) and which is the
   always-on server they reach over SSH. Recommend: heavy work on the faster machine.
2. **How many profiles?** Recommend one per machine unless some work must never share a
   conversation history, settings or bill with the rest (a client, an employer account).
   Each extra profile is a full copy of settings, plugins and rules to maintain.
3. **What to call each profile,** if more than the default. The name is only a label.
4. **Where the projects folder is** (for `ccw`). Recommend one parent folder, with each
   project a subfolder.
5. **Whether to install the git guard** (`git-guard/`). Recommend yes if Claude will run git
   or `gh`: it lets everyday git run without prompts but asks before anything goes public.

## 3. Show the plan, then wait

List every file you'll create or edit, every directory you'll copy, and every command the
user will need to run themselves, labelled by machine. Wait for a yes.

## 4. Set up each profile

For each new profile directory (e.g. `~/.claude-work`):

1. **Aliases and `ccw`:** copy `scripts/profiles.sh` somewhere stable, edit the profile
   names and `PROJECTS_ROOT`, and source it from the shell startup file. Check the file
   still loads (`bash -n` / `zsh -n`).
2. **Moving an existing profile's history in?** Copy all of it in one pass, never piece by
   piece: `projects/`, `jobs/`, `history.jsonl`, `file-history/`, `session-env/`. Merge
   `history.jsonl` rather than overwriting it. Check for ID collisions before copying.
3. **Settings:** copy `settings.json` and `settings.local.json` from the working profile, or
   start from `scripts/settings.example.json`. Nothing carries over by itself. Hooks and
   statuslines that point at files by absolute path must still point at files that exist.
4. **Retention:** set `"cleanupPeriodDays": 9000`. Unset means default pruning; `0` is
   rejected.
5. **Plugins:** with a shared store (`CLAUDE_CODE_PLUGIN_CACHE_DIR`, set in `profiles.sh`),
   install once. Either way, list each plugin in this profile's `enabledPlugins`.
6. **Login:** the user launches the profile once and logs in.

## 5. Git guard (optional)

Run the tests first: `python3 git-guard/test_guard.py --live`. If they pass, give the user
this, labelled with the machine, to run in a normal terminal:

    sudo sh <path-to-repo>/git-guard/install.sh

It installs root-owned, self-tests, then relaxes per-user git prompts in every
`~/.claude*/settings.json`. The user restarts Claude Code sessions afterwards. Repeat on each
machine.

## 6. Second machine

- Repeat steps 1-5 there. Nothing is shared between machines except the account: not
  settings, plugins, memory, conversations or `CLAUDE.md`.
- Write that machine a `CLAUDE.md` with the rules that must apply there, including which
  machine it is and which one is the other.
- Set up the same projects on both as git clones. Tell the user: one instance per repo at a
  time, hand off with a commit, a push and a short handoff note in the repo.
- Suggest renaming the two VS Code terminal tabs after the machines.

## Verify

For every profile touched:

- `scripts/verify-profile.sh <dir>`: every location present, the expected number of deny
  and ask rules, `cleanupPeriodDays` set, the expected plugins enabled.
- `claude plugin list` under that profile.
- The user starts one throwaway session and confirms the statusline shows and a denied
  command is refused. If the git guard is installed: `python3 git-guard/test_guard.py`
  passes and the installer printed `DONE` (it self-tests the installed copy). Never test it
  with a real `gh repo create`.
- If anything looks missing, check the old directory before concluding it's lost.

## Finish

Tell the user what changed and where the backups are. Mention anything left for them to run.
Keep the old profile until they confirm the new one works, then offer to remove it (and ask
before deleting).
