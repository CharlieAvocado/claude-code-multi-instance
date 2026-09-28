# Claude Code profile aliases and a launch-in-project helper.
# Source this from ~/.bashrc or ~/.zshrc:   . /path/to/scripts/profiles.sh
# Edit PROJECTS_ROOT and the profile names to suit.

# One plugin store for every profile: install a plugin once, each profile
# still chooses what it enables. Undocumented variable; see docs/lessons.md.
export CLAUDE_CODE_PLUGIN_CACHE_DIR="$HOME/.claude-plugins"

PROJECTS_ROOT="${PROJECTS_ROOT:-$HOME/projects}"

# One alias per profile. `command claude` skips any alias named claude.
alias claude-work='CLAUDE_CONFIG_DIR=$HOME/.claude-work command claude'
# alias claude-client='CLAUDE_CONFIG_DIR=$HOME/.claude-client command claude'

# Optional: stop bare `claude` from starting the default profile by accident.
# alias claude="echo 'Use a profile alias: claude-work'"

# ccw <project> [claude args...]
# Launches Claude Code inside $PROJECTS_ROOT/<project>, so per-directory state
# (auto-memory, plugins keyed on the working directory) stays per project.
# Profile defaults to "work"; override with CLAUDE_PROFILE=client ccw <project>.
ccw() {
    local proj="$1"
    if [ -z "$proj" ]; then
        echo "usage: ccw <project> [claude args...]" >&2
        ls -1 "$PROJECTS_ROOT" 2>/dev/null | sed 's/^/  /' >&2
        return 2
    fi
    local dir="$PROJECTS_ROOT/$proj"
    [ -d "$dir" ] || { echo "ccw: no such project: $dir" >&2; return 1; }
    local cfg="$HOME/.claude-${CLAUDE_PROFILE:-work}"
    [ -d "$cfg" ] || { echo "ccw: no such profile directory: $cfg" >&2; return 1; }
    shift
    # Subshell, so the calling shell stays where it was.
    ( cd "$dir" && CLAUDE_CONFIG_DIR="$cfg" command claude "$@" )
}
