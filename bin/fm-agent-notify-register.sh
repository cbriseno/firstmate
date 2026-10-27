#!/usr/bin/env bash
# Claude Stop hook: Agent Notify root registration retry (async, never blocks).
#
# Registered in tracked .claude/settings.json beside the other Stop entries.
# Startup registration (fm_notify_register in bin/fm-session-start.sh) cannot
# prove a fresh Claude root: Claude writes the session transcript only after its
# SessionStart hooks finish, and bind needs that transcript's own metadata. At a
# later Stop the transcript exists, so this entry runs the same bind with the
# genuine Stop payload (fm_notify_register_claude_hook in
# bin/fm-agent-notify-lib.sh). Every proof - native session, ancestry, lock,
# session-start completion and lock session - stays bin/fm-agent-notify.py's.
#
# Inert without config/agent-notify.json, in a secondmate home, outside the
# primary scope, on a foreign-host payload, and once this session has any
# binding. Proof failures are silent and ordinary hooks keep their behavior.
# Exit status is always 0. Any argument is a manual run: -h/--help prints usage
# and anything else is refused, both before anything is read.
set -u

usage() {
  cat <<'EOF'
Usage: fm-agent-notify-register.sh

Claude Stop hook registered in .claude/settings.json; not for manual use.
It reads the Stop payload on stdin and, when Agent Notify is configured and
this primary session is not yet bound, retries the root bind. To bind by hand
from inside the native session, run: bin/fm-agent-notify.sh --home <home> bind claude
EOF
}

if [ "$#" -gt 0 ]; then
  case "$1" in
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FM_ROOT="${FM_ROOT_OVERRIDE:-$(cd "$SCRIPT_DIR/.." && pwd)}"
FM_HOME="${FM_HOME:-${FM_ROOT_OVERRIDE:-$FM_ROOT}}"
STATE="${FM_STATE_OVERRIDE:-$FM_HOME/state}"
PAYLOAD=$(cat 2>/dev/null || true)
[ -f "$FM_HOME/config/agent-notify.json" ] || exit 0

# shellcheck source=bin/fm-hook-host-lib.sh
. "$SCRIPT_DIR/fm-hook-host-lib.sh"
# shellcheck source=bin/fm-primary-scope-lib.sh
. "$SCRIPT_DIR/fm-primary-scope-lib.sh"
# shellcheck source=bin/fm-agent-notify-lib.sh
. "$SCRIPT_DIR/fm-agent-notify-lib.sh"

fm_hook_payload_is_foreign_host "$PAYLOAD" && exit 0
fm_primary_scope_matches "$FM_ROOT" "$STATE" || exit 0
fm_notify_register_claude_hook "$PAYLOAD"
exit 0
