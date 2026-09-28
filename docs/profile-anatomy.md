# What's inside a Claude Code profile

Claude Code keeps all of its state in one config directory: `~/.claude` by default, or the
directory named by `CLAUDE_CONFIG_DIR`. Each config directory is a complete, independent
profile. Nothing in one profile is read as a fallback by another.

| Inside the config dir | Holds | What breaks if it's left behind in a move |
|---|---|---|
| `projects/<encoded-cwd>/<session-id>.jsonl` | Conversation transcripts | `/resume` lists nothing |
| `projects/<encoded-cwd>/memory/` | Auto-memory for sessions launched in that directory | Claude forgets preferences it had learned |
| `jobs/<id>/state.json` | Per-session status (done, stopped, blocked, failed) | The conversation list loses its statuses |
| `history.jsonl` | Every prompt typed | Up-arrow history is empty |
| `file-history/<session-id>/` | Record of file edits for undo | Undo history is gone |
| `session-env/<session-id>/` | Per-session environment | Resumed sessions lose their environment |
| `sessions/<pid>.json` | Live process locks | Nothing; these are transient |
| `settings.json`, `settings.local.json` | Permissions, hooks, statusline, model, `enabledPlugins`, UI preferences | The whole settings profile silently stops applying |
| `plugins/`, `skills/` | Installed plugins and skills | Plugins stop loading |
| `.claude.json` | Account, per-project trust flags | Profile looks brand new; trust prompts return |
| `.credentials.json` | The login (Linux; macOS uses the Keychain) | Prompted to log in again |

For the default profile, `.claude.json` sits at `~/.claude.json`, beside the directory
rather than inside it.

**Encoded directories.** Folder names under `projects/` are the working directory with `/`
replaced by `-`, so `/home/user/projects` becomes `-home-user-projects`. `/resume` lists only
sessions whose encoded directory matches the current working directory, and auto-memory is
keyed the same way.

## Things that are easy to get wrong

- **Settings are per profile.** The active profile's `settings.json` is the user settings
  file. Another profile's is not consulted. Test: remove `enabledPlugins` from the active
  profile, run `claude plugin list`, and every plugin reports disabled.
- **`CLAUDE.md` is the exception.** `~/.claude/CLAUDE.md` loads under every profile on that
  machine.
- **Installing a plugin isn't enabling it.** It has to be in the plugin store *and* named in
  the profile's `enabledPlugins`.
- **Absolute paths in settings.** Hooks and statuslines often point at files inside
  `~/.claude` by absolute path. Moving to a new profile doesn't move those files, so leave
  them where they are or update the paths.
- **Retention.** Unset `cleanupPeriodDays` means the built-in pruning window, not "keep
  forever". `0` is rejected. Set a large number (for example 9000, about 25 years) in every
  profile.
- **The conversation list is per profile.** There is no merged view across profiles.

## Sharing state between profiles

- **Plugins:** `CLAUDE_CODE_PLUGIN_CACHE_DIR` relocates the whole plugin store. Point every
  profile at one directory and a plugin installed once is visible to all of them; each still
  chooses what it enables. The variable is undocumented, so if plugins vanish after an update,
  check whether it's still honoured before reinstalling.
- **Conversations:** no supported variable. Symlinking `projects/` and `jobs/` between
  profiles works, but mixes the lists the separate profiles were created to keep apart, and
  two profiles running at once then write to the same `jobs/`.

## Checking a profile

`scripts/verify-profile.sh [config-dir]` lists each location, counts entries, and prints the
permission rule counts, hooks, retention and enabled plugins from `settings.json`.
