# Bearings rows on the same live lab: base 7880f5e vs target 549fdc9

Lab: real tmux server (private fm-lab socket), crew busy/idle recorded by bin/fm-busy-event.sh, status lines appended as crews do; snapshot taken 2026-10-27T19:01:15Z after the transition step.

## Underway (in_flight)

| id | state | base: state_source / wait_until / hold_bucket | target: state_source | target: wait_until | target: hold_bucket / hold_until |
|---|---|---|---|---|---|
| api-crew | working | absent / absent / absent | pane | null | null / null |
| docs-crew | working | absent / absent / absent | pane | null | null / null |
| held-live-working | working | absent / absent / absent | pane | null | live / null |
| paused-untimed | paused | absent / absent / absent | status-log | null | null / null |
| paused-vendor | working | absent / absent / absent | pane | null | null / null |
| resumed-validation | paused | absent / absent / absent | status-log | 2026-10-28T23:40:00Z | null / null |
| ui-crew | working | absent / absent / absent | pane | null | null / null |
| waits-publication | paused | absent / absent / absent | status-log | 2026-10-27T01:00:00Z | null / null |
| mate/mate-build | working | absent / absent / absent | pane | null | null / null |
| mate/mate-vendor | working | absent / absent / absent | pane | null | null / null |

## Charted Next (gates)

| id | reason (display) | base: hold_bucket / hold_until | target: hold_bucket | target: hold_until | blocked_by |
|---|---|---|---|---|---|
| held-dated | until 2026-11-03: resume after travel | absent / absent | dated | 2026-11-03 | - |
| follow-a | - | absent / absent | null | null | ui-crew |
| follow-b | - | absent / absent | null | null | api-crew |
| follow-c | - | absent / absent | null | null | follow-a |
| deferred-call | until 2026-11-10: revisit pricing | absent / absent | dated | 2026-11-10 | - |
