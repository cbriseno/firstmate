# shellcheck shell=bash
# Optional transition integration; schema/commands owned by fm-agent-notify.py.
# All failures are visible but never roll back an already authoritative change.
# No config means no subprocesses, no records and no notification behavior change.
_FM_NOTIFY_BIN=${BASH_SOURCE[0]%/*}/fm-agent-notify.sh

fm_notify_enabled() {
  [ -n "${FM_HOME:-}" ] && [ -f "$FM_HOME/config/agent-notify.json" ] \
    && [ ! -e "$FM_HOME/.fm-secondmate-home" ]
}

fm_notify_call() {  # <task> <occurrence> <needs-decision|resolved> <hold-set>
  fm_notify_enabled || return 0
  local state=open
  [ "$3" != resolved ] || state=resolved
  bash "$_FM_NOTIFY_BIN" --home "$FM_HOME" call "$1" "$2" "$state" --at "$4" \
    || printf 'warning: Agent Notify captain-call transition remains unaccepted for %s\n' "$1" >&2
}

fm_notify_register() {
  fm_notify_enabled || return 0
  local provider
  if [ -n "${CODEX_THREAD_ID:-}" ]; then provider=codex
  elif [ -n "${CLAUDE_CODE_SESSION_ID:-}" ]; then provider=claude
  else return 0
  fi
  printf '{}' | bash "$_FM_NOTIFY_BIN" --home "$FM_HOME" bind "$provider" >/dev/null \
    || printf 'warning: Agent Notify native supervisor identity was not proven; ordinary hooks remain enabled\n' >&2
}

fm_notify_landed() {  # <data> <task> <tasks-axi done artifact flags...>
  fm_notify_enabled || return 0
  local data=$1 id=$2 artifact='' verb='' kind='' flag hold_kind row
  shift 2
  # Only explicit pre-landing designations can produce an alert.
  [ -f "$FM_HOME/data/agent-notify/designate/$id.json" ] || return 0
  while [ "$#" -ge 2 ]; do
    flag=$1
    case "$flag" in
      --pr) verb=merged; artifact=$2 ;;
      --report) verb=reported; artifact=$2; kind=scout ;;
      --note) [ "$2" != 'local main' ] || { verb='done'; artifact=$2; } ;;
    esac
    shift 2
  done
  [ -n "$artifact" ] || return 0
  if ! fm_backlog_row_probe "$data" "$id"; then
    printf 'warning: Agent Notify cannot verify landed backlog row %s\n' "$id" >&2
    return 0
  fi
  [ "${FM_BACKLOG_ROW_STATE%% *}" = 'done' ] || return 0
  hold_kind=$FM_BACKLOG_ROW_HOLD_KIND
  [ -z "${FM_BACKLOG_ROW_KIND:-}" ] || kind=$FM_BACKLOG_ROW_KIND
  row=$(jq -n --arg kind "$kind" --arg hold "$hold_kind" --arg verb "$verb" --arg artifact "$artifact" \
    '{state:"done",structured:true,kind:$kind,hold_kind:$hold,completion:{verb:$verb}}
     + (if $verb == "merged" then {pr_url:$artifact}
        elif $verb == "reported" then {report_path:$artifact}
        else {local_note:$artifact} end)') || return 0
  printf '%s' "$row" | bash "$_FM_NOTIFY_BIN" --home "$FM_HOME" landed "$id" \
    || printf 'warning: Agent Notify landing transition remains unaccepted for %s\n' "$id" >&2
}
