# Lessons from a profile migration

A default `~/.claude` setup was moved to a named profile (`~/.claude-work` in the examples
here) over three days. Creating the directory and the alias took minutes. Making the new
profile behave like the old one took four repair passes, each triggered by a symptom rather
than a check. Nothing was ever lost; every gap was data still sitting in the old directory.

## What happened

1. **Day 1.** Aliases added and the new config directory created by hand. No record was kept
   of the exact steps.
2. **Day 2.** `/resume` in the new profile showed only the current session. All transcripts
   were still in `~/.claude/projects/`. Moving `projects/` fixed `/resume`.
3. **Day 3.** The conversation list showed conversations but not their statuses. Only
   `projects/` had moved; the statuses live in `jobs/`, and `history.jsonl`, `file-history/`
   and `session-env/` had been left behind the same way. Moved and merged, no ID collisions.
4. **Day 3, while documenting.** Two more gaps with no symptom at all:
   - The plugins were installed only in `~/.claude/plugins/`, so none loaded in the new
     profile.
   - The whole settings file was still only in `~/.claude`. The new profile had run for two
     days with no force-push deny list, no ask rules on commit or push, no hooks and no
     statusline.

## What to take from it

- **Move by checklist, not by symptom.** Every gap was the same mistake: moving the piece
  that had a visible symptom and assuming the rest came with it. `docs/profile-anatomy.md`
  lists everything that has to move together.
- **The dangerous gaps are silent.** A session without a deny list looks exactly like one
  with a deny list. Settings and plugins were found only by reading the directory on purpose.
  Run `scripts/verify-profile.sh` after any profile change.
- **A plugin that stops loading takes its side effects with it.** A memory plugin quietly
  stopped writing its daily rollups the day sessions moved profiles. When a plugin's output
  goes missing, check that it's loaded before debugging it.
- **The launch directory matters as much as the profile.** Plugins and auto-memory that key
  on the working directory put everything launched from one parent folder into one shared
  slot. Every session was launched from `~/projects` (the folder that holds every project),
  so for over two weeks the memory plugin's end-of-session summary for one project
  overwrote the summary for another. Launch inside the project folder (`ccw` in `scripts/profiles.sh`).
  Anything that must survive across sessions belongs in a file in the project, not in
  per-session state.
- **Record setup steps.** The directories and aliases were created by hand with no record, so
  the exact first step can't be reconstructed. Do setup inside a Claude session, or write it
  down.

## A repo made public without asking

While this guide was being prepared, Claude created its GitHub repo as public without asking.
Two things went wrong.

1. **An instruction was read as permission.** The user said which account the repo should
   go under. Claude took that as a yes to create it, and chose public. Naming an account,
   a location or a repo name says where, not whether or how visible.
2. **The ask rule didn't fire.** The settings had an `ask` rule for `gh repo create*`, but
   the command was `gh auth switch --user ... && gh repo create ... --public`. Claude Code's
   permission rules match the start of the command, so a command placed after `&&` got
   through. The git guard's push check did stop the push, but by then the repo already
   existed and was public (empty, until the user approved the push).

What changed:

- The git guard now inspects every command in a line, including after `&&` or `;` and
  inside `bash -c "..."` or `$(...)`. It asks before any `gh` command that creates or
  publishes something: repo create, visibility edits, gists, releases, PRs, writing
  `gh api` calls, and unknown aliases or extensions. The command that slipped through is
  now a test case.
- **Don't rely on permission-rule patterns alone for anything irreversible.** A prefix
  match is easy to sidestep, even by accident. Put a hook that parses the whole command in
  front of the actions that matter.
- **Say "create it as private or public?" in so many words, and default to private.** A
  private repo can be made public later; a public one may already have been seen or copied.

## The multi-account plan that didn't happen

The original plan was one profile per account, to keep separate work fully apart. It stopped
after the first profile, which absorbed everything and became the only one in use. In
hindsight, a second account would have needed its own login, its own copy of every setting,
rule, hook and plugin choice, its own retention setting, and would have produced a
conversation list that can never be merged with the first. The only real gain is a separate
usage limit.

Split accounts when the separation is the point: work that must never share a history or a
bill, like a client or an employer account. To keep projects apart on one account, launching
inside each project folder and naming sessions by project covers most of it.

Unused profile directories are worth deleting. Installers that hook "every profile" (the git
guard here does) keep modifying them.
