#!/usr/bin/env bash
# Hermetic producer contract through the public CLI and real fixture processes.
# No real hooks, native prompts, notification DB, network, phone or services.
set -eu
# shellcheck source=tests/lib.sh disable=SC1091
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
TASK_TMP=$(fm_test_tmproot fm-agent-notify)
PYTHONUNBUFFERED=1 python3 "$ROOT/tests/fm-agent-notify-cases.py" "$ROOT" "$TASK_TMP"
