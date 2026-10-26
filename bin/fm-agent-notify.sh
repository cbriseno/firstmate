#!/usr/bin/env bash
# Optional Firstmate producer bridge. No config means no side effects.
# Usage: fm-agent-notify.sh --home <absolute-home> <command> [args...]
# Commands and durable schema: bin/fm-agent-notify.py --help.
# `landed <task-id>` takes one canonical backlog row on stdin and delegates
# artifact eligibility to fm-landed-lib.sh, excluding its display-only fallback.
# Install `hook <codex|claude>` as the REPLACEMENT Agent Notify hook command,
# never in parallel with it. This script does not install hooks or publish ntfy.
set -eu
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
if [ "${1:-}" = --home ] && [ "${3:-}" = landed ]; then
  # shellcheck source=bin/fm-landed-lib.sh
  . "$SCRIPT_DIR/fm-landed-lib.sh"
  row=$(jq -ce "$FM_LANDED_JQ_DEFS
    select(.state == \"done\" and .structured == true and landed_delivery)
    | {artifact:landed_artifact,verb:.completion.verb}" ) || exit 1
  printf '%s' "$row" | python3 "$SCRIPT_DIR/fm-agent-notify.py" "$@"
else
  exec python3 "$SCRIPT_DIR/fm-agent-notify.py" "$@"
fi
