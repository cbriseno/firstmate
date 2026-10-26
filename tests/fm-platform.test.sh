#!/usr/bin/env bash
# Platform route classification and early refusal before operational writes.
# Shim classifications are contract tests, never evidence of execution on an OS.
set -eu
# shellcheck source=tests/lib.sh disable=SC1091
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
TASK_TMP=$(fm_test_tmproot fm-platform)
mkdir -p "$TASK_TMP/fakebin"
cat > "$TASK_TMP/fakebin/uname" <<'SH'
#!/usr/bin/env bash
case "${1:-}" in
  -r) printf '%s\n' "$TEST_RELEASE" ;;
  *) printf '%s\n' "$TEST_KERNEL" ;;
esac
SH
chmod +x "$TASK_TMP/fakebin/uname"
export PATH="$TASK_TMP/fakebin:$PATH"
export TEST_KERNEL TEST_RELEASE
TEST_RELEASE=generic
# shellcheck source=bin/fm-platform-lib.sh disable=SC1091
. "$ROOT/bin/fm-platform-lib.sh"
for pair in 'Linux linux' 'Darwin macos' 'MINGW64_NT windows-shell' 'MSYS_NT windows-shell' 'CYGWIN_NT windows-shell' 'FreeBSD unsupported'; do
  read -r TEST_KERNEL expected <<< "$pair"
  [ "$(fm_platform_name)" = "$expected" ] || fail "platform classification: $expected"
done
TEST_KERNEL=Linux
TEST_RELEASE=6.6.87.2-microsoft-standard-WSL2
[ "$(fm_platform_name)" = wsl2 ] || fail 'WSL2 route'
fm_platform_require || fail 'WSL2 classification acceptance'
TEST_RELEASE=4.4.0-Microsoft
[ "$(fm_platform_name)" = wsl1 ] || fail 'WSL1 classification'
if fm_platform_require 2>/dev/null; then fail 'WSL1 must refuse'; fi
TEST_KERNEL=MINGW64_NT
export FM_HOME="$TASK_TMP/untouched-home"
for command in fm-session-start.sh fm-bootstrap.sh fm-spawn.sh fm-doctor.sh; do
  rc=0
  bash "$ROOT/bin/$command" > "$TASK_TMP/result" 2>&1 || rc=$?
  [ "$rc" = 2 ] || fail "$command unsupported-platform exit"
  [ ! -e "$FM_HOME" ] || fail "$command wrote an unsupported home"
  assert_contains "$(cat "$TASK_TMP/result")" PLATFORM_UNSUPPORTED "$command explains WSL2 route"
done
printf 'PASS: platform classifications and four fail-closed entry points (simulated kernels)\n'
