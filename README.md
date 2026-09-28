# Running more than one Claude Code

A working setup for running Claude Code under separate profiles, and for using one Claude
account from two machines side by side: a local Mac and an always-on Linux server, both
driven from terminals in VS Code on the Mac. It includes the lessons from getting there, a
setup checklist, and the scripts used.

**Terms:**

- **The Mac:** the local macOS machine where the editor runs.
- **The Linux server:** an always-on Linux machine reached over SSH from the Mac. It hosts
  scheduled jobs, dashboards, and a Claude Code profile of its own.

**Contents:**

| Path | What it is |
|---|---|
| `README.md` | This guide |
| `docs/profile-anatomy.md` | What's inside a profile, and what breaks when a piece is left behind |
| `docs/lessons.md` | What went wrong migrating to a named profile, and the multi-account plan that was dropped |
| `scripts/profiles.sh` | Profile aliases, a shared plugin store, and `ccw` (launch inside a project) |
| `scripts/verify-profile.sh` | Checks that a profile is whole |
| `scripts/settings.example.json` | Starter settings: retention and a small deny/ask list |
| `git-guard/` | Lets Claude run git freely but asks before anything goes public |

The session-title hook and the git guard described below were built as part of the author's
custom Claude Code dashboard setup, not taken from Claude Code itself. The git guard runs
standalone and is included. The session-title hook reads its settings from that dashboard, so
it's described but not included.

## The short version

- **A config directory is a whole profile.** Transcripts, statuses, prompt history, undo,
  settings, plugins, login. Move all of it or none of it.
- **Nothing falls back to `~/.claude`.** A new profile starts with no permission rules, no
  hooks, no plugins and no statusline. The one exception is `~/.claude/CLAUDE.md`, which
  every profile on that machine reads.
- **Missing isn't lost.** When a profile looks empty, the data is usually in the other
  directory. Check every location before concluding anything is gone.
- **Set up by checklist, not by symptom.** The dangerous gaps (settings, plugins) have no
  visible symptom. A session with no deny list looks exactly like one with a deny list.
- **One account is simpler.** A second account means a second login, a second copy of every
  rule and hook, and conversation lists that can never be merged. Only split when the
  separation is the point.
- **Each machine is its own world.** Same account, but the Mac and server instances share no
  conversations, settings, memory or plugins. Keep them in step deliberately.
- **Never let both instances work the same repo at once.** They're separate clones; git is
  what syncs them.

## Profiles on one machine

Claude Code keeps all of its state in `~/.claude`, or in whatever directory
`CLAUDE_CONFIG_DIR` names. Each such directory is a separate profile, with its own login,
conversation list, settings and plugins. `docs/profile-anatomy.md` has the full list of what's
inside one.

`scripts/profiles.sh` sets up:

- **An alias per profile,** e.g. `claude-work` runs Claude Code with
  `CLAUDE_CONFIG_DIR=~/.claude-work`. Optionally, bare `claude` can be aliased to a reminder so
  nothing starts in the default profile by accident.
- **A shared plugin store** (`CLAUDE_CODE_PLUGIN_CACHE_DIR`), so a plugin installed once is
  visible to every profile. Each profile still enables its own.
- **`ccw <project>`,** which launches inside `~/projects/<project>` in a subshell. Auto-memory
  and plugins that key on the working directory then keep separate state per project instead
  of piling everything into one slot.

A profile name is only a label. Nothing about the name scopes what the profile can work on.

## One account, two machines, side by side

**The arrangement:** VS Code on the Mac with two terminal panels.

- **Server panel:** SSH'd into the Linux server, running Claude Code under a named profile,
  working in `~/projects`.
- **Mac panel:** plain `claude` (default `~/.claude` profile), working in the Mac's own
  checkout folder (`~/Documents/GitHub` here).

### What's shared and what isn't

| | Shared | Separate per machine |
|---|---|---|
| Login / account | yes | |
| Usage limits | yes: both draw from one plan's allowance | |
| Conversation list, `/resume` | | yes |
| Settings, permission rules, hooks | | yes |
| Plugins | | yes |
| `CLAUDE.md` | | yes |
| Auto-memory, memory plugins | | yes |
| Repos | via git only | separate clones |

Memory is the row that causes trouble. Whatever one instance learns about the user's
preferences stays in that machine's profile. The other instance never sees it, and can repeat
a mistake the first one stopped making. Anything both need to know belongs in a file in the
repo (a README, a HANDOFF.md), not in either instance's memory.

### What to keep the same on both

- **Git guard** (`git-guard/`): installed root-owned on each machine, so both instances get
  the same "never make it public without asking" rule whatever their own settings say.
- **Session titles:** a `UserPromptSubmit` hook that names every session
  `<project> YYYY-MM-DD-HHMM · <task>`. The task label comes from one small-model call on
  the first prompt. It adds a `/done` command that marks a finished session in the
  conversation list. Settings live on the server's dashboard; the Mac's copy fetches them and
  keeps the last copy for when the server is off. Worth copying as an idea: when two machines
  each have their own conversation list, names that carry the project and the time are what
  make the lists readable.
- **API keys:** one key store in the same place on both machines, synced from the Mac.

Anything else wanted on both (a new hook, a plugin, the retention setting) has to be done
twice. The git guard installer updates every `~/.claude*/settings.json` on the machine it
runs on, so run it once per machine.

### Working side by side

- **Tell the panels apart.** Rename the VS Code terminal tabs "Mac" and "Server"
  (right-click the tab, Rename), and check the `user@host` in each shell prompt. `~` and
  `~/projects` can exist on both with different contents, so a path alone never shows which
  machine a panel is on.
- **One repo, one instance at a time.** The two machines hold separate clones. If both edit
  the same repo at once, the result is a merge instead of a handoff. For a repo worked on
  from both, a simple rule helps: the Mac works on `main`, the server works on its own branch
  (a hook can refuse server pushes to `main`), and the Mac merges the server branch in.
- **Hand off through git and a file.** Finish on one machine with a commit, a push and a
  short handoff note; start on the other with a pull and that note. Neither instance can
  read the other's conversation.
- **SSH runs one way.** The Mac can reach the server; the server can't reach the Mac. The
  server instance can prepare a script or a commit, but anything that runs on the Mac is run
  by the user or by the Mac instance.
- **Put heavy work on the faster machine.** Here the server is an older laptop, and an OCR
  workload ran about 15x faster once moved to the Mac. The server suits always-on work:
  dashboards, timers, scheduled jobs, file transfer.
- **Label every command with its machine.** Ask both instances to say whether a command runs
  on the Mac or on the server (after SSHing in). Paste bare commands, never with a leading
  `!`: that's a Claude prompt convention, and in a real shell `! cmd && next` silently skips
  `next`.

## Checklist: adding a profile or a machine

1. Log in (`claude`, or the profile's alias) and accept the trust prompt in the working
   folder.
2. Copy `settings.json` and `settings.local.json` from a working profile, or start from
   `scripts/settings.example.json`: deny/ask/allow rules, hooks, statusline, output style.
3. Set `cleanupPeriodDays` to a large number (9000). Unset means default pruning, and `0` is
   rejected.
4. Install plugins and list them in the profile's `enabledPlugins`. With a shared store,
   confirm `CLAUDE_CODE_PLUGIN_CACHE_DIR` is exported before the aliases.
5. On a new machine, run `sudo sh git-guard/install.sh`.
6. Set up the session-naming hook, API keys and anything else that should match the other
   machine.
7. On a new machine, write a `CLAUDE.md` with the rules that must apply there. It won't
   inherit the other machine's.
8. Run `scripts/verify-profile.sh <config-dir>` and `claude plugin list`, then start one
   throwaway session and confirm the statusline shows and a denied command is refused.
