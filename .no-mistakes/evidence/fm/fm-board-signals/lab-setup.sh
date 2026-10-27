#!/usr/bin/env bash
# Disposable live lab for the bearings structured-signal change.
# Mints two marked lab homes (main + one registered secondmate), starts a REAL
# tmux server on a private fm-lab socket with one window per crew, records crew
# busy/idle through the real hook writer (bin/fm-busy-event.sh, which Claude's
# hooks call), and appends status declarations exactly as crews do (>> state/<id>.status).
# Prints the lab paths. Teardown: lab-teardown.sh <LAB> <MATE>.
set -eu
ROOT=${ROOT:?run from the gate worktree with ROOT set}
LAB=$(mktemp -d /tmp/fm-lab.XXXXXX)
MATE=$(mktemp -d /tmp/fm-lab-mate.XXXXXX)
"$ROOT/bin/fm-lab-home.sh" create "$LAB" >/dev/null
"$ROOT/bin/fm-lab-home.sh" create "$MATE" >/dev/null
mkdir -p "$LAB/tmux" "$MATE/bin"
printf '# Firstmate lab secondmate\n' > "$MATE/AGENTS.md"
printf 'mate\n' > "$MATE/.fm-secondmate-home"
printf -- '- mate - lab domain (home: %s; scope: lab; projects: sample; added 2026-10-27)\n' "$MATE" > "$LAB/data/secondmates.md"

T() { TMUX_TMPDIR="$LAB/tmux" tmux -L fm-lab "$@"; }

cat > "$LAB/data/backlog.md" <<'EOF'
## In flight
- [ ] ui-crew - Board legend for live work (repo: sample) (kind: ship) (since 2026-10-27)
- [ ] api-crew - Expose crew signals API (repo: sample) (kind: ship) (since 2026-10-27)
- [ ] docs-crew - Document the deck columns (repo: sample) (kind: ship) (since 2026-10-27)
- [ ] paused-vendor - Wait for vendor window (repo: sample) (kind: ship) (since 2026-10-26)
- [ ] paused-untimed - Wait for upstream release (repo: sample) (kind: ship) (since 2026-10-26)
- [ ] resumed-validation - Fix after own validation run (repo: sample) (kind: ship) (since 2026-10-26)
- [ ] held-dated - Stopped until captain date (repo: sample) (kind: captain) (hold: resume after travel) (hold-kind: captain) (hold-until: 2026-11-03)
  Captain hold set: 2026-10-25T00:00:00Z
- [ ] held-live-working - Working while captain decides (repo: sample) (kind: captain) (hold: choose release route) (hold-kind: captain)
  Captain hold set: 2026-10-25T00:00:00Z
- [ ] waits-publication - Waits on board legend landing blocked-by: ui-crew (repo: sample) (kind: ship) (since 2026-10-26)

## Queued
- [ ] follow-a - Follow-up after legend blocked-by: ui-crew (repo: sample) (kind: ship)
- [ ] follow-b - Follow-up after API blocked-by: api-crew (repo: sample) (kind: ship)
- [ ] follow-c - Follow-up of follow-a blocked-by: follow-a (repo: sample) (kind: ship)
- [ ] deferred-call - Deferred by captain to a date (repo: sample) (kind: captain) (hold: revisit pricing) (hold-kind: captain) (hold-until: 2026-11-10)
  Captain hold set: 2026-10-20T00:00:00Z

## Done
EOF

cat > "$MATE/data/backlog.md" <<'EOF'
## In flight
- [ ] mate-build - Secondmate build work (repo: sample) (kind: ship) (since 2026-10-27)
- [ ] mate-vendor - Secondmate vendor wait (repo: sample) (kind: ship) (since 2026-10-27)
- [ ] mate-resumed - Secondmate resumed after pause (repo: sample) (kind: ship) (since 2026-10-27)

## Queued

## Done
EOF

first=1
crew() {  # <home> <id> <busy|idle> [status lines...]
  local home=$1 id=$2 sem=$3 gen event line
  shift 3
  mkdir -p "$home/projects/$id"
  if [ "$first" = 1 ]; then
    T new-session -d -s firstmate -n "fm-$id" -x 200 -y 50 "printf 'crew %s\n' $id; exec sleep 86400"
    first=0
  else
    T new-window -d -t firstmate: -n "fm-$id" "printf 'crew %s\n' $id; exec sleep 86400"
  fi
  printf '%s\n' "window=firstmate:fm-$id" "worktree=$home/projects/$id" "project=sample" \
    "harness=claude" "kind=ship" "mode=no-mistakes" > "$home/state/$id.meta"
  case "$sem" in busy) event=user-prompt-submit ;; idle) event=stop ;; esac
  gen=$(FM_HOME="$home" "$ROOT/bin/fm-busy-event.sh" arm "$home/state" "$id")
  FM_HOME="$home" "$ROOT/bin/fm-busy-event.sh" apply "$home/state" "$id" "$sem" --gen "$gen" \
    --source claude-hook --event "$event"
  : > "$home/state/$id.status"
  for line in "$@"; do printf '%s\n' "$line" >> "$home/state/$id.status"; done
}

now=$(date -u +%s)
crew "$LAB" ui-crew busy "working [at=$now]: building the board legend"
crew "$LAB" api-crew busy "working [at=$now]: wiring crew signals"
crew "$LAB" docs-crew busy "working [at=$now]: documenting columns"
crew "$LAB" paused-vendor idle "paused [at=$now]: vendor maintenance window until 2026-10-28T15:00Z"
crew "$LAB" paused-untimed idle "paused [at=$now]: waiting for the upstream release"
# Adversarial: crew declared a timed pause for its own validation run, the run
# returned and the crew resumed fixing silently (busy pane, no later status line).
crew "$LAB" resumed-validation busy "paused [at=$now]: own validation run until 2026-10-28T23:40Z"
crew "$LAB" held-dated idle "paused [at=$now]: stopped for captain until 2026-11-03"
crew "$LAB" held-live-working busy "working [at=$now]: preparing both release routes"
crew "$LAB" waits-publication idle "paused [at=$now]: waiting on ui-crew publication"

crew "$MATE" mate-build busy "working [at=$now]: secondmate building"
crew "$MATE" mate-vendor idle "paused [at=$now]: vendor window until 2026-10-29T09:30Z"
crew "$MATE" mate-resumed busy "paused [at=$now]: own validation run until 2026-10-28T20:00Z"

sock=$(T display-message -p '#{socket_path}')
pid=$(T display-message -p '#{pid}')
printf 'LAB=%s\nMATE=%s\nLAB_TMUX=%s,%s,0\n' "$LAB" "$MATE" "$sock" "$pid"
