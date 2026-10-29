#!/usr/bin/env bash
# fm-tasks-axi.sh - run tasks-axi against THIS home's backlog from any working directory.
#
# Usage: fm-tasks-axi.sh [<tasks-axi command> [args...]]
#        fm-tasks-axi.sh --help
#
# Every routine firstmate backlog read or mutation goes through this command
# rather than a bare `tasks-axi`; `fm-tasks-axi.sh <command> --help` prints
# tasks-axi's own help. Arguments reach tasks-axi as given, apart from one
# rewrite that keeps file arguments meaning what the caller meant: a relative
# value of `--to` or any `--*-file` flag (`--body-file`, `--relation-file`, ...)
# is made absolute against the caller's working directory, because tasks-axi
# starts from the backlog root instead. `--report` stays as given: tasks-axi
# stores it verbatim as a link, which lifecycle transitions record relative to
# that same root.
#
# `show` (including `view`) and `list` decode stored captain-hold reasons
# through bin/fm-hold-reason-lib.sh, which owns the field-only decoding contract.
# Decoded reasons use quoted strings so embedded line breaks remain intact.
#
# Why it exists: a bare `tasks-axi` resolves the tracked `.tasks.toml` paths
# against its working directory, so from the code root it forks the queue
# whenever the home lives elsewhere; docs/configuration.md ("Backlog backend")
# owns that rationale.
#
# Addressing is bin/fm-backlog-transition-lib.sh's fm_backlog_tasks_axi_addressing,
# the same resolution the lifecycle transitions use: tasks-axi runs from the
# configured data directory's parent, so that home's own `.tasks.toml` (or
# tasks-axi's built-in defaults, which keep the archive beside the backlog)
# supplies the adapter, done_keep, and the archive path; a markdown backlog is
# additionally pinned to `<data>/backlog.md` through TASKS_AXI_FILE. The
# environment carries the pin rather than a trailing --file so the no-command
# dashboard works too. A configured non-markdown adapter is addressed by that
# root alone, so an inherited TASKS_AXI_FILE is cleared for it.
#
# The data directory is FM_DATA_OVERRIDE, else $FM_HOME/data, else the code
# root's data/ (FM_HOME unset keeps the single-home layout unchanged).
#
# Refusals (exit 2, nothing run):
#   - tasks-axi missing from PATH;
#   - a caller-supplied --file, because this command owns the addressing and
#     tasks-axi would silently let the last --file win;
#   - `add` (or its `create` alias) with --start, so neither spelling places a
#     row In flight without the dispatch artifacts bin/fm-spawn.sh creates -
#     the task record, status file, and inbox that go with the row - which such
#     a row would lack, counting as live work nobody is doing that nothing
#     later would notice (`start <id>` stays a documented direct transition);
#   - `hold` with `--kind captain`, because a captain call opened here would
#     carry no card for the captain to answer: bin/fm-captain-hold.sh hold is
#     the one path that opens one, and it refuses a call without choices;
#   - a data directory that cannot be resolved, or whose backend configuration
#     cannot be read (bin/fm-tasks-axi-lib.sh owns that diagnostic);
#   - a markdown `<data>/backlog.md` that is itself a symlink, because the
#     first write would replace the link with a private copy, exactly the fork
#     this command exists to prevent. Lifecycle transitions refuse the same file.
# Otherwise the exit status is tasks-axi's own, unless decoding a read fails;
# in that case the decoder's nonzero status is returned.
# New successful done/close transitions preserve an optional owner completion
# receipt through fm-backlog-transition-lib.sh; retries retain the old instant.
# start/reopen invalidate that receipt. Receipt failures warn without changing
# a successful backend result; unavailable proof retains date-only history.
#
# Home-owned presentation extension (not a tasks-axi backend mutation):
#   presentation <id> [--json]                         Read the saved declaration.
#   presentation <id> --summary TEXT [--waiting-for TEXT] [--next-action TEXT]
#   presentation <id> --presentation-file /path/to/object.json
#   presentation <id> --clear
# Optional fields are summary, waiting_for, next_action: plain text (1..2000
# characters) or null; summary is best kept within 280 characters. Writes patch
# only supplied fields, empty text clears one field, --clear clears all three.
# File input is the same partial object; unknown keys/types are rejected.
# The existing backlog owner verifies the exact task before writing private
# data/<id>/presentation.json atomically. This is an authored declaration with
# its own source/time, never a status transition, liveness signal or refresh
# heartbeat. Reads never renew it; unknown fields remain null. No wake is sent.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FM_ROOT="${FM_ROOT_OVERRIDE:-$(cd "$SCRIPT_DIR/.." && pwd)}"
FM_HOME="${FM_HOME:-${FM_ROOT_OVERRIDE:-$FM_ROOT}}"
DATA="${FM_DATA_OVERRIDE:-$FM_HOME/data}"
# shellcheck source=bin/fm-tasks-axi-lib.sh disable=SC1091
. "$SCRIPT_DIR/fm-tasks-axi-lib.sh"
# shellcheck source=bin/fm-backlog-transition-lib.sh disable=SC1091
. "$SCRIPT_DIR/fm-backlog-transition-lib.sh"
# shellcheck source=bin/fm-hold-reason-lib.sh disable=SC1091
. "$SCRIPT_DIR/fm-hold-reason-lib.sh"

usage() {
  awk '
    NR == 1 { next }
    /^#/ { sub(/^# ?/, ""); print; next }
    { exit }
  ' "$0"
}

fail() {
  printf 'fm-tasks-axi: %s\n' "$*" >&2
  exit 2
}

case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
  presentation)
    shift
    case "${1:-}" in
      -h|--help) usage; exit 0 ;;
      ''|-*) fail 'presentation requires a task id; use --help' ;;
    esac
    presentation_id=$1
    shift
    export FM_HOME
    exec python3 "$SCRIPT_DIR/fm_delivery.py" presentation --task "$presentation_id" --data "$DATA" "$@"
    ;;
esac

if [ "${1:-}" = hold ]; then
  previous_arg=''
  for arg in "$@"; do
    case "$previous_arg $arg" in
      '--kind captain'|*' --kind=captain')
        fail "a captain hold opens a captain call; use bin/fm-captain-hold.sh hold, which records the card the captain answers"
        ;;
    esac
    previous_arg=$arg
  done
fi

CALLER_DIR=$(pwd)

absolute_from_caller() {  # <path-value>
  case "$1" in
    ''|-|/*) printf '%s' "$1" ;;
    *) printf '%s/%s' "$CALLER_DIR" "$1" ;;
  esac
}

ARGS=()
path_value_next=0
for arg in "$@"; do
  if [ "$path_value_next" = 1 ]; then
    ARGS+=("$(absolute_from_caller "$arg")")
    path_value_next=0
    continue
  fi
  case "$arg" in
    --file|--file=*)
      fail "this command always addresses this home's backlog at $DATA; drop --file, or run tasks-axi directly for another backlog"
      ;;
    --start)
      case "${1:-}" in
        add|create)
          fail "add --start would place a row In flight with no dispatch record; add it Queued and let bin/fm-spawn.sh start it"
          ;;
      esac
      ARGS+=("$arg")
      ;;
    --to|--*-file)
      ARGS+=("$arg")
      path_value_next=1
      ;;
    --to=*|--*-file=*)
      ARGS+=("${arg%%=*}=$(absolute_from_caller "${arg#*=}")")
      ;;
    *)
      ARGS+=("$arg")
      ;;
  esac
done

command -v tasks-axi >/dev/null 2>&1 || fail "tasks-axi is not on PATH; run bin/fm-bootstrap.sh for the install command"

FM_BACKLOG_TRANSITION_ERROR=
if ! fm_backlog_tasks_axi_addressing "$DATA"; then
  fail "${FM_BACKLOG_TRANSITION_ERROR:-data directory cannot be resolved: $DATA}"
fi

if [ -n "$FM_BACKLOG_AXI_FILE" ]; then
  if [ -L "$FM_BACKLOG_AXI_FILE" ]; then
    fail "$FM_BACKLOG_AXI_FILE is a symlink; a tasks-axi write would replace it with a regular file and fork the backlog - make it this home's real file"
  fi
  export TASKS_AXI_FILE="$FM_BACKLOG_AXI_FILE"
else
  unset TASKS_AXI_FILE
fi

cd "$FM_BACKLOG_AXI_ROOT" || fail "cannot enter the backlog root $FM_BACKLOG_AXI_ROOT"
case "${1:-}" in
  show|view|list)
    set -o pipefail
    tasks-axi ${ARGS[@]+"${ARGS[@]}"} | fm_hold_reason_decode_stream
    exit $?
    ;;
  done|close)
    case "${2:-}" in
      ''|-*) exec tasks-axi ${ARGS[@]+"${ARGS[@]}"} ;;
    esac
    previous_state=''
    previous_hold=''
    if fm_backlog_row_probe "$DATA" "$2"; then
      previous_state=${FM_BACKLOG_ROW_STATE%% *}
      previous_hold=$FM_BACKLOG_ROW_HOLD_KIND
    fi
    tasks-axi ${ARGS[@]+"${ARGS[@]}"}
    result=$?
    if [ "$result" -eq 0 ] && [ -n "$previous_state" ] && [ "$previous_state" != 'done' ] && [ "$previous_hold" != captain ]; then
      fm_backlog_record_completion "$DATA" "$2" ''
    fi
    exit "$result"
    ;;
  start|reopen)
    tasks-axi ${ARGS[@]+"${ARGS[@]}"}
    result=$?
    [ "$result" -ne 0 ] || fm_backlog_invalidate_completion "$DATA" "${2:-}"
    exit "$result"
    ;;
esac
exec tasks-axi ${ARGS[@]+"${ARGS[@]}"}
